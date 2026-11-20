import json
import os
import sys
from pathlib import Path

if sys.stdin is None:
    sys.stdin = open(os.devnull, encoding="utf-8")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def resource_dir() -> str:
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


LEGACY_DATA_DIR = "DAMp"


def default_library() -> str:
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        root = os.path.join(home, "Library", "Application Support")
    elif os.name == "nt":
        root = os.environ.get("APPDATA", home)
    else:
        root = os.path.join(home, ".local", "share")
    base, legacy = os.path.join(root, "DAM"), os.path.join(root, LEGACY_DATA_DIR)
    if not os.path.exists(base) and os.path.isdir(legacy):
        os.rename(legacy, base)
    return os.path.join(base, "library")


def selfcheck() -> int:
    info = {"python": sys.version.split()[0]}
    for label, module in (("pillow", "PIL"), ("numpy", "numpy"), ("opencv", "cv2"), ("pi_heif", "pi_heif"), ("imagecapture", "ImageCaptureCore"), ("quartz", "Quartz"), ("cryptography", "cryptography")):
        try:
            imported = __import__(module)
            info[label] = getattr(imported, "__version__", "ok")
        except Exception as exc:
            info[label] = f"missing: {exc}"
    from app.config import VERSION

    info["dam"] = VERSION
    info["dist_bundled"] = os.path.isdir(os.path.join(resource_dir(), "frontend_dist"))
    info["models_bundled"] = all(
        os.path.isfile(os.path.join(resource_dir(), "models", name))
        for name in ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx")
    )
    print(json.dumps(info))
    return 0


def _serve(port: int) -> None:
    import uvicorn

    from app.main import app as fastapi_app

    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")


class _Tee:
    def __init__(self, stream, log) -> None:
        self._stream, self._log = stream, log

    def write(self, text):
        try:
            self._log.write(text)
        except Exception:
            pass
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def log_folder() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, "Library", "Logs", "formDAM") if sys.platform == "darwin" else os.path.dirname(default_library())


def _open_log():
    from app import startup

    frozen = getattr(sys, "frozen", False)
    if not frozen and getattr(sys.stderr, "name", None) != os.devnull:
        return None
    folder = log_folder()
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        return None
    startup.keep_errors(Path(folder))
    if not frozen:
        return None
    try:
        log = open(os.path.join(folder, "engine.log"), "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    import faulthandler
    import time

    log.write(f"\n=== formDAM engine start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    faulthandler.enable(file=log)
    sys.stdout, sys.stderr = _Tee(sys.stdout, log), _Tee(sys.stderr, log)
    return log


def main() -> int:
    if "--selfcheck" in sys.argv:
        return selfcheck()
    if len(sys.argv) > 1 and sys.argv[1] == "--share":
        from app import macshare

        return macshare.run(sys.argv[2:])
    return serve()


def _release(lock) -> None:
    from app import startup

    if startup.number(startup.read_lock(lock).get("pid")) == os.getpid():
        try:
            lock.unlink()
        except OSError:
            pass


def _watch_shell(lock) -> None:
    from app import startup

    shell = startup.shell_pid()
    if shell <= 1:
        return

    def leave() -> None:
        try:
            print(f"formDAM engine: the app that started this engine is gone (process {shell}), stopping", flush=True)
        except (OSError, ValueError):
            pass
        _release(lock)
        os._exit(0)

    startup.watch(shell, leave)


def serve() -> int:
    from app import libraries, startup

    _open_log()
    if startup.alone():
        beside = startup.app_beside(Path(sys.executable))
        if beside is not None and startup.open_app(beside):
            print(f"formDAM engine: started without its app, so it opened {beside} and stopped", flush=True)
            return 0
        print(f"formDAM engine: started without its app, and no app program was found near {sys.executable}", flush=True)
        print("formdam-backend is a part of FormDAM and serves nothing on its own. Open FormDAM instead.", file=sys.stderr, flush=True)
        return 4
    data = Path(os.path.abspath(libraries.config_dir()))
    try:
        data.mkdir(parents=True, exist_ok=True)
        lock, replaced = startup.claim(data, startup.shell_pid())
    except startup.Busy as err:
        print(err, file=sys.stderr, flush=True)
        return 2
    except OSError as err:
        print(f"formDAM cannot use its data folder: {err}", file=sys.stderr, flush=True)
        return 5
    if replaced:
        print(f"formDAM engine: an engine left running without its app was stopped (process {replaced})", flush=True)
    _watch_shell(lock)
    os.environ.setdefault("FORMDAM_DIST", os.path.join(resource_dir(), "frontend_dist"))
    os.environ.setdefault("FORMDAM_MODELS", os.path.join(resource_dir(), "models"))
    os.environ.setdefault("FORMDAM_LIBRARY", libraries.current() or default_library())
    port = int(os.environ.get("FORMDAM_PORT", "0") or 0)
    import signal

    def ended(_signum, _frame) -> None:
        _release(lock)
        os._exit(0)

    signal.signal(signal.SIGTERM, ended)

    def run() -> None:
        try:
            _serve(port)
        finally:
            _release(lock)

    if sys.platform == "darwin":
        from app.services import iccsvc

        if iccsvc.available():
            import threading

            server = threading.Thread(target=run, name="formDAM-engine", daemon=True)
            server.start()

            def _exit_with_server() -> None:
                server.join()
                os._exit(0)

            threading.Thread(target=_exit_with_server, name="formDAM-exit", daemon=True).start()
            iccsvc.start_native()
            from PyObjCTools import AppHelper

            AppHelper.runConsoleEventLoop()
            return 0
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
