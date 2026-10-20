"""iPhone/iPad import via Apple's ImageCaptureCore, the same framework Photos.app
& Image Capture use. PyObjC (MIT) binds it; no usbmuxd protocol code, no GPL.

The process MAIN thread must pump the CFRunLoop for delegate callbacks to fire:
desktop_entry owns that (uvicorn moves to a worker thread on macOS). Jobs &
request threads coordinate w/ the main-thread callbacks over threading.Events.
The bridge is injectable so the orchestration is testable off-macOS.
"""

import os
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

SESSION_TIMEOUT = 45.0
CATALOG_TIMEOUT = 300.0
DOWNLOAD_TIMEOUT = 240.0
THUMB_TIMEOUT = 15.0
DELETE_TIMEOUT = 90.0

LOCKED_GUIDANCE = (
    "The device is locked or this Mac is not trusted yet. Unlock the device, tap "
    "Trust This Computer, & approve the connection if asked (iOS 26: Settings > "
    "Privacy & Security > Wired Accessories)."
)

_bridge_factory: Optional[Callable[[], Any]] = None
_bridge: Optional[Any] = None
_lock = threading.Lock()
_loop_owner = False
_start_error = ""


def _icc_importable() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import ImageCaptureCore  # noqa: F401

        return True
    except Exception:
        return False


def available() -> bool:
    return _bridge_factory is not None or _icc_importable()


def active() -> bool:
    return _bridge is not None


def detail() -> Dict[str, Any]:
    reason = ""
    if not available():
        reason = "ImageCaptureCore not present (pyobjc-framework-ImageCaptureCore is bundled by build_macos_app)" if sys.platform == "darwin" else "macOS only"
    elif not active():
        reason = _start_error or "engine not started in desktop mode (run the formDAM app, or python3 desktop_entry.py)"
    return {"available": available(), "active": active(), "loop": "main" if _loop_owner else "none", "reason": reason}


def start_native() -> bool:
    """Create the browser & begin watching for devices. Must run on the process
    main thread, before that thread enters the run loop (desktop_entry does both)."""
    global _bridge, _loop_owner, _start_error
    with _lock:
        if _bridge is not None:
            return True
        try:
            factory = _bridge_factory or _RealBridge
            bridge = factory()
            bridge.start()
        except Exception as exc:
            _start_error = f"{type(exc).__name__}: {exc}"
            return False
        _bridge = bridge
        _loop_owner = threading.current_thread() is threading.main_thread()
        return True


def ensure_test_bridge() -> None:
    global _bridge
    with _lock:
        if _bridge is None and _bridge_factory is not None:
            _bridge = _bridge_factory()
            _bridge.start()


def reset_for_tests() -> None:
    global _bridge, _loop_owner, _start_error
    with _lock:
        _bridge = None
        _loop_owner = False
        _start_error = ""


def list_devices() -> List[Dict[str, Any]]:
    if _bridge_factory is not None:
        ensure_test_bridge()
    if _bridge is None:
        return []
    out = []
    for dev in _bridge.devices():
        out.append({
            "serial": dev["serial"],
            "name": dev.get("name") or "iPhone",
            "state": "locked-or-untrusted" if dev.get("restricted") else "ready",
            "via": "icc",
        })
    return out


def owns(serial: str) -> bool:
    return any(dev["serial"] == serial for dev in list_devices())


def contents(serial: str) -> Dict[str, Any]:
    if _bridge_factory is not None:
        ensure_test_bridge()
    if _bridge is None:
        raise RuntimeError("iPhone engine is not running; open the formDAM desktop app")
    _bridge.open_session(serial, SESSION_TIMEOUT)
    _bridge.wait_ready(serial, CATALOG_TIMEOUT)
    return _bridge.media_files(serial)


def device_thumb(serial: str, key: int, gen: int) -> Optional[bytes]:
    if _bridge is None:
        return None
    return _bridge.thumbnail(serial, key, gen, THUMB_TIMEOUT)


def close_device(serial: str) -> None:
    if _bridge is None:
        return
    try:
        _bridge.close_session(serial)
    except Exception:
        pass


def run_import(
    serial: str,
    state: Dict[str, Any],
    import_file: Callable[[str], Dict[str, Any]],
    tmpdir: str,
    keys: Optional[List[int]] = None,
    gen: Optional[int] = None,
    delete_after: bool = False,
    link_pair: Optional[Callable[[int, int], bool]] = None,
) -> None:
    if _bridge is None:
        raise RuntimeError("iPhone engine is not running; open the formDAM desktop app")
    counts = state["counts"]
    state["stage"] = "connecting"
    _bridge.open_session(serial, SESSION_TIMEOUT)
    state["stage"] = "reading the photo catalog"
    _bridge.wait_ready(serial, CATALOG_TIMEOUT)
    if gen is None:
        listing = _bridge.media_files(serial)
        gen = listing["gen"]
        files = listing["files"]
    else:
        files = _bridge.listing_for(serial, gen)
    if keys is not None:
        wanted = set(keys)
        files = [entry for entry in files if entry["key"] in wanted]
    counts["found"] = len(files)
    state["stage"] = "copying"
    deletable: List[int] = []
    for entry in files:
        state["current"] = entry["name"]
        try:
            subdir = os.path.join(tmpdir, f"k{entry['key']}")
            os.makedirs(subdir, exist_ok=True)
            got = _bridge.download(serial, entry["key"], gen, subdir, DOWNLOAD_TIMEOUT)
            extras = [os.path.join(subdir, extra) for extra in got.get("extras", []) if extra]
            photo_id: Optional[int] = None
            video_id: Optional[int] = None
            statuses: List[str] = []
            for path in [got.get("path", ""), *extras]:
                if not path or not os.path.isfile(path):
                    continue
                result = import_file(path)
                status = result.get("status") or ""
                statuses.append(status)
                if status == "imported":
                    counts["imported"] += 1
                elif status == "duplicate":
                    counts["duplicates"] += 1
                else:
                    counts["skipped"] += 1
                media_id = result.get("media_id")
                if media_id and status in ("imported", "duplicate"):
                    kind = result.get("kind") or _kind_of(path)
                    if kind == "image" and photo_id is None:
                        photo_id = media_id
                    elif kind == "video" and video_id is None:
                        video_id = media_id
            if photo_id and video_id and link_pair is not None:
                link_pair(photo_id, video_id)
            if statuses and all(s in ("imported", "duplicate") for s in statuses):
                deletable.append(entry["key"])
        except Exception:
            counts["failed"] += 1
            continue
    if delete_after and deletable:
        state["stage"] = "deleting imported items from the device"
        error = _bridge.delete_files(serial, deletable, gen, DELETE_TIMEOUT)
        state["deleted"] = 0 if error else len(deletable)
        if error:
            state["delete_error"] = error
    state["stage"] = "finished"


def _kind_of(path: str) -> Optional[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext in {".mov", ".mp4", ".m4v", ".3gp", ".avi"}:
        return "video"
    if ext in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tif", ".tiff", ".dng"}:
        return "image"
    return None


class _Slot:
    def __init__(self) -> None:
        self.session_evt = threading.Event()
        self.session_error = ""
        self.ready_evt = threading.Event()
        self.dl_evt = threading.Event()
        self.dl_error = ""
        self.dl_saved = ""
        self.dl_extras: List[str] = []
        self.del_evt = threading.Event()
        self.del_error = ""


class _RealBridge:
    def __init__(self) -> None:
        import Foundation
        import ImageCaptureCore
        from PyObjCTools import AppHelper

        self.icc = ImageCaptureCore
        self.foundation = Foundation
        self.call_after = AppHelper.callAfter
        self.lock = threading.RLock()
        self.registry: Dict[str, Dict[str, Any]] = {}
        self.delegate: Any = None
        self.browser: Any = None
        self._thumb_pending: Dict[Any, Dict[str, Any]] = {}
        try:
            import Quartz

            self.quartz: Any = Quartz
        except Exception:
            self.quartz = None

    def start(self) -> None:
        cls = _delegate_class(self.foundation)
        self.delegate = cls.alloc().init()
        self.delegate.bridge = self
        icc = self.icc
        browser = icc.ICDeviceBrowser.alloc().init()
        browser.setDelegate_(self.delegate)
        browser.setBrowsedDeviceTypeMask_(icc.ICDeviceTypeMaskCamera | icc.ICDeviceLocationTypeMaskLocal)
        browser.start()
        self.browser = browser

    def _uuid(self, device: Any) -> str:
        try:
            value = device.UUIDString()
        except Exception:
            value = None
        return str(value) if value else str(device.name() or id(device))

    def _restricted(self, device: Any) -> bool:
        try:
            return bool(device.isAccessRestrictedAppleDevice())
        except Exception:
            return False

    def on_add(self, device: Any) -> None:
        try:
            device.setDelegate_(self.delegate)
        except Exception:
            pass
        serial = self._uuid(device)
        with self.lock:
            self.registry[serial] = {
                "device": device,
                "serial": serial,
                "name": str(device.name() or "iPhone"),
                "restricted": self._restricted(device),
                "slot": _Slot(),
                "files": [],
                "meta": [],
                "gen": 0,
                "open": False,
                "thumb_cache": {},
            }

    def on_remove(self, device: Any) -> None:
        serial = self._uuid(device)
        with self.lock:
            entry = self.registry.pop(serial, None)
        if entry:
            entry["slot"].session_error = "The device was unplugged."
            entry["slot"].session_evt.set()
            entry["slot"].dl_error = "The device was unplugged."
            entry["slot"].dl_evt.set()
            entry["slot"].del_error = "The device was unplugged."
            entry["slot"].del_evt.set()

    def on_restriction(self, device: Any, restricted: bool) -> None:
        with self.lock:
            entry = self.registry.get(self._uuid(device))
            if entry:
                entry["restricted"] = restricted

    def on_session(self, device: Any, error: Any) -> None:
        with self.lock:
            entry = self.registry.get(self._uuid(device))
        if entry:
            entry["slot"].session_error = _err_str(error)
            entry["slot"].session_evt.set()

    def on_ready(self, device: Any) -> None:
        with self.lock:
            entry = self.registry.get(self._uuid(device))
        if entry:
            entry["slot"].ready_evt.set()

    def on_downloaded(self, options: Any, error: Any) -> None:
        entry = self._current_dl
        if entry is None:
            return
        slot = entry["slot"]
        slot.dl_error = _err_str(error)
        saved, extras = "", []
        if options is not None:
            try:
                saved = str(options.get(self.icc.ICSavedFilename) or "")
                anc = options.get(self.icc.ICSavedAncillaryFiles)
                extras = [str(x) for x in anc] if anc else []
            except Exception:
                pass
        slot.dl_saved = saved
        slot.dl_extras = extras
        slot.dl_evt.set()

    _current_dl: Optional[Dict[str, Any]] = None

    def devices(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [
                {"serial": e["serial"], "name": e["name"], "restricted": e["restricted"]}
                for e in self.registry.values()
            ]

    def _entry(self, serial: str) -> Dict[str, Any]:
        with self.lock:
            entry = self.registry.get(serial)
        if entry is None:
            raise RuntimeError("That device is no longer connected; replug it & retry.")
        return entry

    def open_session(self, serial: str, timeout: float) -> None:
        entry = self._entry(serial)
        if entry["open"]:
            if entry["restricted"]:
                raise RuntimeError(LOCKED_GUIDANCE)
            return
        slot = entry["slot"]
        slot.session_evt.clear()
        slot.session_error = ""
        self.call_after(entry["device"].requestOpenSession)
        if not slot.session_evt.wait(timeout):
            raise RuntimeError(
                "Timed out talking to the device. " + (LOCKED_GUIDANCE if entry["restricted"] else "Replug the cable & retry.")
            )
        err = slot.session_error
        if err and "already open" not in err.lower():
            if entry["restricted"] or "-9943" in err or "-21343" in err:
                raise RuntimeError(LOCKED_GUIDANCE)
            raise RuntimeError(f"Could not open the device: {err}")
        if entry["restricted"]:
            raise RuntimeError(LOCKED_GUIDANCE)
        entry["open"] = True

    def wait_ready(self, serial: str, timeout: float) -> None:
        entry = self._entry(serial)
        if not entry["slot"].ready_evt.wait(timeout):
            raise RuntimeError("The device never finished listing its photos. Keep it unlocked & retry.")

    def media_files(self, serial: str) -> Dict[str, Any]:
        entry = self._entry(serial)
        done = threading.Event()
        out: List[Dict[str, Any]] = []

        def snapshot() -> None:
            files = entry["device"].mediaFiles() or []
            keep = []
            for index, item in enumerate(files):
                meta: Dict[str, Any] = {"key": index, "name": f"IMG_{index:05d}", "size": 0, "date": None, "duration": None}
                try:
                    meta["name"] = str(item.name() or meta["name"])
                    meta["size"] = int(item.fileSize() or 0)
                except Exception:
                    pass
                try:
                    stamp = item.creationDate()
                    if stamp is not None:
                        meta["date"] = float(stamp.timeIntervalSince1970())
                except Exception:
                    pass
                try:
                    length = item.duration()
                    if length:
                        meta["duration"] = float(length)
                except Exception:
                    pass
                keep.append(item)
                out.append(meta)
            entry["files"] = keep
            entry["meta"] = out
            entry["gen"] += 1
            entry["thumb_cache"] = {}
            done.set()

        self.call_after(snapshot)
        if not done.wait(30.0):
            raise RuntimeError("Could not read the device photo list; keep the device unlocked & retry.")
        return {"gen": entry["gen"], "files": out}

    def listing_for(self, serial: str, gen: int) -> List[Dict[str, Any]]:
        entry = self._entry(serial)
        if gen != entry["gen"]:
            raise RuntimeError("The device contents changed; reopen the device & retry.")
        return list(entry["meta"])

    def thumbnail(self, serial: str, key: int, gen: int, timeout: float) -> Optional[bytes]:
        entry = self._entry(serial)
        if gen != entry["gen"]:
            return None
        cached = entry["thumb_cache"].get(key)
        if cached is not None:
            return cached
        files = entry["files"]
        if key < 0 or key >= len(files):
            return None
        item = files[key]
        handle = self._item_handle(item, key)
        pending = {"evt": threading.Event(), "data": None}
        with self.lock:
            self._thumb_pending[handle] = pending
        self.call_after(item.requestThumbnail)
        if not pending["evt"].wait(timeout):
            with self.lock:
                self._thumb_pending.pop(handle, None)
            return None
        data = pending["data"]
        if data:
            entry["thumb_cache"][key] = data
        return data

    def _item_handle(self, item: Any, fallback: int) -> Any:
        try:
            handle = int(item.ptpObjectHandle() or 0)
            if handle:
                return handle
        except Exception:
            pass
        try:
            return f"{item.name()}|{int(item.fileSize() or 0)}"
        except Exception:
            return f"idx-{fallback}"

    def on_thumb(self, item: Any, thumb: Any, error: Any) -> None:
        handle = self._item_handle(item, -1)
        with self.lock:
            pending = self._thumb_pending.pop(handle, None)
        if pending is None:
            return
        if error is None and thumb is not None:
            pending["data"] = self._encode_jpeg(thumb)
        pending["evt"].set()

    def _encode_jpeg(self, cgimage: Any) -> Optional[bytes]:
        if self.quartz is None:
            return None
        try:
            data = self.foundation.NSMutableData.data()
            dest = self.quartz.CGImageDestinationCreateWithData(data, "public.jpeg", 1, None)
            if dest is None:
                return None
            self.quartz.CGImageDestinationAddImage(dest, cgimage, {self.quartz.kCGImageDestinationLossyCompressionQuality: 0.72})
            if not self.quartz.CGImageDestinationFinalize(dest):
                return None
            return bytes(data)
        except Exception:
            return None

    def delete_files(self, serial: str, keys: List[int], gen: int, timeout: float) -> str:
        entry = self._entry(serial)
        if gen != entry["gen"]:
            return "The device contents changed; nothing was deleted."
        files = entry["files"]
        items = [files[k] for k in keys if 0 <= k < len(files)]
        if not items:
            return ""
        slot = entry["slot"]
        slot.del_evt.clear()
        slot.del_error = ""

        def request() -> None:
            entry["device"].requestDeleteFiles_(items)

        self.call_after(request)
        if not slot.del_evt.wait(timeout):
            return "Timed out deleting from the device."
        return slot.del_error

    def on_delete_done(self, device: Any, error: Any) -> None:
        with self.lock:
            entry = self.registry.get(self._uuid(device))
        if entry:
            entry["slot"].del_error = _err_str(error)
            entry["slot"].del_evt.set()

    def download(self, serial: str, key: int, gen: int, dest_dir: str, timeout: float) -> Dict[str, Any]:
        entry = self._entry(serial)
        if gen != entry["gen"]:
            raise RuntimeError("The device contents changed; reopen the device & retry.")
        files = entry["files"]
        if key < 0 or key >= len(files):
            raise RuntimeError("stale file handle")
        item = files[key]
        slot = entry["slot"]
        slot.dl_evt.clear()
        slot.dl_error = ""
        slot.dl_saved = ""
        slot.dl_extras = []
        self._current_dl = entry
        icc, foundation = self.icc, self.foundation
        requested = str(item.name())

        def request() -> None:
            options = {
                icc.ICDownloadsDirectoryURL: foundation.NSURL.fileURLWithPath_(dest_dir),
                icc.ICSaveAsFilename: requested,
                icc.ICOverwrite: True,
                icc.ICDownloadSidecarFiles: True,
            }
            entry["device"].requestDownloadFile_options_downloadDelegate_didDownloadSelector_contextInfo_(
                item, options, self.delegate, b"didDownloadFile:error:options:contextInfo:", 0
            )

        self.call_after(request)
        if not slot.dl_evt.wait(timeout):
            raise RuntimeError(f"Timed out downloading {item.name()}")
        if slot.dl_error:
            raise RuntimeError(slot.dl_error)
        saved = slot.dl_saved or requested
        path = os.path.join(dest_dir, saved)
        if not os.path.isfile(path):
            fallback = os.path.join(dest_dir, str(item.name()))
            path = fallback if os.path.isfile(fallback) else path
        return {"path": path, "extras": list(slot.dl_extras)}

    def close_session(self, serial: str) -> None:
        try:
            entry = self._entry(serial)
        except Exception:
            return
        entry["open"] = False
        entry["gen"] += 1
        entry["thumb_cache"] = {}
        self.call_after(entry["device"].requestCloseSession)


def _err_str(error: Any) -> str:
    if error is None:
        return ""
    try:
        return f"{error.localizedDescription()} (code {error.code()})"
    except Exception:
        return str(error)


_DelegateClass: Any = None


def _delegate_class(foundation: Any) -> Any:
    global _DelegateClass
    if _DelegateClass is not None:
        return _DelegateClass

    class FormDAMICCDelegate(foundation.NSObject):
        bridge = None

        def deviceBrowser_didAddDevice_moreComing_(self, browser, device, more):
            if self.bridge:
                self.bridge.on_add(device)

        def deviceBrowser_didRemoveDevice_moreGoing_(self, browser, device, more):
            if self.bridge:
                self.bridge.on_remove(device)

        def deviceBrowser_deviceDidChangeName_(self, browser, device):
            pass

        def deviceBrowserDidEnumerateLocalDevices_(self, browser):
            pass

        def device_didOpenSessionWithError_(self, device, error):
            if self.bridge:
                self.bridge.on_session(device, error)

        def device_didCloseSessionWithError_(self, device, error):
            pass

        def deviceDidBecomeReady_(self, device):
            pass

        def deviceDidBecomeReadyWithCompleteContentCatalog_(self, device):
            if self.bridge:
                self.bridge.on_ready(device)

        def deviceDidChangeName_(self, device):
            pass

        def device_didEncounterError_(self, device, error):
            if self.bridge:
                self.bridge.on_session(device, error)

        def didRemoveDevice_(self, device):
            if self.bridge:
                self.bridge.on_remove(device)

        def cameraDevice_didAddItems_(self, device, items):
            pass

        def cameraDevice_didRemoveItems_(self, device, items):
            pass

        def cameraDevice_didRenameItems_(self, device, items):
            pass

        def cameraDevice_didReceiveThumbnail_forItem_error_(self, device, thumb, item, error):
            if self.bridge:
                self.bridge.on_thumb(item, thumb, error)

        def cameraDevice_didReceiveMetadata_forItem_error_(self, device, meta, item, error):
            pass

        def cameraDeviceDidChangeCapability_(self, device):
            pass

        def cameraDevice_didCompleteDeleteFilesWithError_(self, device, error):
            if self.bridge:
                self.bridge.on_delete_done(device, error)

        def cameraDevice_didReceivePTPEvent_(self, device, event):
            pass

        def cameraDeviceDidRemoveAccessRestriction_(self, device):
            if self.bridge:
                self.bridge.on_restriction(device, False)

        def cameraDeviceDidEnableAccessRestriction_(self, device):
            if self.bridge:
                self.bridge.on_restriction(device, True)

        def didDownloadFile_error_options_contextInfo_(self, file, error, options, context):
            if self.bridge:
                self.bridge.on_downloaded(options, error)

        def didReceiveDownloadProgressForFile_downloadedBytes_maxBytes_(self, file, downloaded, total):
            pass

    _DelegateClass = FormDAMICCDelegate
    return _DelegateClass
