"""iPhone/iPad import facade: native ImageCaptureCore first (iccsvc, the
Photos.app path), usbmuxd + AFC (pymobiledevice3) as the optional fallback.

The device must be unlocked & trusted ("Trust This Computer"; iOS 26 adds the
Wired Accessories approval). Lazy imports keep cold start fast & make the AFC
dependency optional; factories are injectable for tests.
"""

import os
import sys
import tempfile
from typing import Any, Callable, Dict, List, Optional

from . import classify, iccsvc, libraryfs

MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tif", ".tiff",
    ".dng", ".mov", ".mp4", ".m4v", ".3gp", ".avi",
}

_lockdown_factory: Optional[Callable[[str], Any]] = None
_afc_factory: Optional[Callable[[Any], Any]] = None
_list_factory: Optional[Callable[[], List[Any]]] = None


def _afc_state() -> Dict[str, str]:
    if _list_factory is not None:
        return {"available": "yes", "reason": ""}
    if sys.platform != "darwin":
        return {"available": "no", "reason": "macOS only"}
    try:
        import pymobiledevice3  # noqa: F401
    except Exception:
        return {"available": "no", "reason": "pymobiledevice3 not installed (optional fallback; the native path does not need it)"}
    try:
        from importlib.metadata import version

        major = int(version("pymobiledevice3").split(".")[0])
    except Exception:
        major = 0
    if major >= 8:
        return {"available": "no", "reason": "pymobiledevice3 8+ is async-only; pip install 'pymobiledevice3<8' for the fallback path"}
    return {"available": "yes", "reason": ""}


def afc_available() -> bool:
    return _afc_state()["available"] == "yes"


def supported() -> bool:
    return iccsvc.available() or iccsvc.active() or afc_available()


def status_detail() -> Dict[str, Any]:
    native = iccsvc.detail()
    afc = _afc_state()
    hint = ""
    if not supported():
        hint = native["reason"] if sys.platform == "darwin" else "iPhone import needs the macOS desktop app"
    elif not native["active"] and native["available"]:
        hint = native["reason"]
    return {
        "supported": supported(),
        "platform": sys.platform,
        "native": native,
        "afc": afc,
        "hint": hint,
    }


def _list_devices_raw() -> List[Any]:
    if _list_factory is not None:
        return _list_factory()
    from pymobiledevice3 import usbmux

    return usbmux.list_devices()


def _lockdown(serial: str, autopair: bool) -> Any:
    if _lockdown_factory is not None:
        return _lockdown_factory(serial)
    from pymobiledevice3.lockdown import create_using_usbmux

    return create_using_usbmux(serial=serial, autopair=autopair)


def _afc(lockdown: Any) -> Any:
    if _afc_factory is not None:
        return _afc_factory(lockdown)
    from pymobiledevice3.services.afc import AfcService

    return AfcService(lockdown)


def list_devices() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = list(iccsvc.list_devices())
    seen = {entry["serial"] for entry in out}
    if not afc_available():
        return out
    for dev in _list_devices_raw():
        serial = getattr(dev, "serial", None) or str(dev)
        if serial in seen:
            continue
        seen.add(serial)
        entry: Dict[str, Any] = {"serial": serial, "name": None, "state": "ready", "via": "afc"}
        try:
            lockdown = _lockdown(serial, autopair=False)
            info = getattr(lockdown, "all_values", None) or {}
            entry["name"] = info.get("DeviceName") or getattr(lockdown, "display_name", None) or "iPhone"
        except Exception as exc:
            entry["state"] = "locked-or-untrusted"
            entry["detail"] = type(exc).__name__
        out.append(entry)
    return out


def _walk_media(afc: Any, base: str = "/DCIM") -> List[str]:
    files: List[str] = []
    try:
        names = afc.listdir(base)
    except Exception:
        return files
    for name in names:
        if name in (".", ".."):
            continue
        path = f"{base}/{name}"
        ext = os.path.splitext(name)[1].lower()
        if ext in MEDIA_EXTS:
            files.append(path)
            continue
        if "." not in name:
            files.extend(_walk_media(afc, path))
    return files


def _pull_file(afc: Any, remote: str, local: str) -> None:
    pull = getattr(afc, "pull", None)
    if callable(pull):
        pull(remote, local)
        if os.path.isfile(local):
            return
        candidate = os.path.join(local, os.path.basename(remote)) if os.path.isdir(local) else local
        if os.path.isfile(candidate):
            os.replace(candidate, local) if candidate != local else None
            return
    data = afc.get_file_contents(remote)
    with open(local, "wb") as handle:
        handle.write(data)


def contents(serial: str) -> Dict[str, Any]:
    if not iccsvc.owns(serial):
        raise RuntimeError("Browsing device contents needs the native engine; this device is on the fallback path, use Import All.")
    listing = iccsvc.contents(serial)
    for entry in listing["files"]:
        kind, _ = classify.media_kind(entry["name"])
        entry["kind"] = kind or "image"
    return listing


def device_thumb(serial: str, key: int, gen: int) -> Optional[bytes]:
    return iccsvc.device_thumb(serial, key, gen)


def close_device(serial: str) -> None:
    iccsvc.close_device(serial)


def run_import(
    serial: str,
    state: Dict[str, Any],
    keys: Optional[List[int]] = None,
    gen: Optional[int] = None,
    delete_after: bool = False,
) -> None:
    counts = {"found": 0, "imported": 0, "duplicates": 0, "skipped": 0, "failed": 0}
    state["counts"] = counts
    if iccsvc.owns(serial):
        with tempfile.TemporaryDirectory(prefix="dam-idevice-") as tmp:
            iccsvc.run_import(
                serial,
                state,
                lambda path: libraryfs.import_one(path, move=True),
                tmp,
                keys=keys,
                gen=gen,
                delete_after=delete_after,
                link_pair=libraryfs.link_live,
            )
        return
    state["stage"] = "connecting"
    lockdown = _lockdown(serial, autopair=True)
    afc = _afc(lockdown)
    state["stage"] = "scanning"
    files = _walk_media(afc)
    counts["found"] = len(files)
    state["stage"] = "copying"
    with tempfile.TemporaryDirectory(prefix="dam-idevice-") as tmp:
        for remote in files:
            state["current"] = os.path.basename(remote)
            local = os.path.join(tmp, os.path.basename(remote))
            try:
                _pull_file(afc, remote, local)
                result = libraryfs.import_one(local, move=True)
            except Exception:
                counts["failed"] += 1
                continue
            status = result.get("status")
            if status == "imported":
                counts["imported"] += 1
            elif status == "duplicate":
                counts["duplicates"] += 1
            else:
                counts["skipped"] += 1
    state["stage"] = "finished"
