import json
import os
import sys


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


def _open_log():
    if not getattr(sys, "frozen", False):
        return None
    home = os.path.expanduser("~")
    folder = os.path.join(home, "Library", "Logs", "formDAM") if sys.platform == "darwin" else os.path.dirname(default_library())
    try:
        os.makedirs(folder, exist_ok=True)
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
    _open_log()
    os.environ.setdefault("FORMDAM_DIST", os.path.join(resource_dir(), "frontend_dist"))
    os.environ.setdefault("FORMDAM_MODELS", os.path.join(resource_dir(), "models"))
    from app import libraries

    os.environ.setdefault("FORMDAM_LIBRARY", libraries.current() or default_library())
    port = int(os.environ.get("FORMDAM_PORT", "0") or 0)
    if sys.platform == "darwin":
        from app.services import iccsvc

        if iccsvc.available():
            import threading

            server = threading.Thread(target=_serve, args=(port,), name="formDAM-engine", daemon=True)
            server.start()

            def _exit_with_server() -> None:
                server.join()
                os._exit(0)

            threading.Thread(target=_exit_with_server, name="formDAM-exit", daemon=True).start()
            iccsvc.start_native()
            from PyObjCTools import AppHelper

            AppHelper.runConsoleEventLoop()
            return 0
    _serve(port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
