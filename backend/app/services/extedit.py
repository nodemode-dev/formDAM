import os
import shutil
import threading
import time
from typing import Any, Callable, Dict, Optional

from ..config import library_root
from ..db import q1, reset_thread_conn
from . import decode, editsvc, filesvc, libraryfs

POLL_S = 1.5
MAX_AGE_S = 12 * 3600
KEEP = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif", ".webp"}

_lock = threading.Lock()
_sessions: Dict[int, Dict[str, Any]] = {}
_thread: Optional[threading.Thread] = None


def edits_dir() -> str:
    return os.path.join(library_root(), "edits")


def work_dir() -> str:
    return os.path.join(edits_dir(), "work")


def external_path(state: Dict[str, Any]) -> Optional[str]:
    ext = state.get("external") if isinstance(state, dict) else None
    name = os.path.basename(str((ext or {}).get("file") or ""))
    if not name:
        return None
    path = os.path.join(edits_dir(), name)
    return path if os.path.isfile(path) else None


def _working_copy(row) -> str:
    os.makedirs(work_dir(), exist_ok=True)
    stamp = int(time.time())
    src = libraryfs.abs_path(row["rel_path"])
    ext = os.path.splitext(row["name"])[1].lower()
    state = editsvc.edits_of(row["id"])
    if not state and ext in KEEP:
        dest = os.path.join(work_dir(), f"{row['id']}-{stamp}{ext}")
        shutil.copy2(src, dest)
        return dest
    img = editsvc.render_still(row["id"], src, None) if state else None
    if img is None:
        img = decode.open_image(src, row["name"], max_long=None, develop=True)
    if img is None:
        raise ValueError("This file could not be decoded")
    dest = os.path.join(work_dir(), f"{row['id']}-{stamp}.tif")
    img.convert("RGB").save(dest, "TIFF", compression="tiff_lzw")
    return dest


def start(media_id: int, app: Optional[str], store: Callable[[int, Dict[str, Any]], Any]) -> Dict[str, Any]:
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    work = _working_copy(row)
    st = os.stat(work)
    with _lock:
        _sessions[media_id] = {"work": work, "app": app or "", "name": row["name"], "mtime": st.st_mtime, "size": st.st_size,
                               "pending": None, "started": time.time(), "adopted": 0, "store": store}
    if not filesvc.open_with(work, app):
        with _lock:
            _sessions.pop(media_id, None)
        raise OSError("The application could not be opened")
    _ensure_thread()
    return status(media_id)


def status(media_id: int) -> Dict[str, Any]:
    with _lock:
        s = _sessions.get(media_id)
        if s is None:
            return {"active": False, "adopted": 0}
        return {"active": True, "app": s["app"], "adopted": s["adopted"], "started": s["started"]}


def stop(media_id: int) -> None:
    with _lock:
        s = _sessions.pop(media_id, None)
    if s:
        try:
            os.unlink(s["work"])
        except OSError:
            pass


def _adopt(media_id: int, s: Dict[str, Any]) -> None:
    name = os.path.basename(s["work"])
    probe = decode.open_image(s["work"], name, max_long=256)
    if probe is None:
        return
    os.makedirs(edits_dir(), exist_ok=True)
    stem, ext = os.path.splitext(name)
    dest = os.path.join(edits_dir(), f"{stem}-{s['adopted'] + 1}{ext}")
    shutil.copy2(s["work"], dest)
    previous = external_path(editsvc.edits_of(media_id))
    s["store"](media_id, {"external": {"file": os.path.basename(dest), "app": s["app"], "ts": time.time()}})
    if previous and previous != dest:
        try:
            os.unlink(previous)
        except OSError:
            pass
    s["adopted"] += 1


def _tick() -> None:
    now = time.time()
    with _lock:
        items = list(_sessions.items())
    for media_id, s in items:
        if now - s["started"] > MAX_AGE_S or not os.path.isfile(s["work"]):
            stop(media_id)
            continue
        st = os.stat(s["work"])
        sig = (st.st_mtime, st.st_size)
        if sig == (s["mtime"], s["size"]):
            s["pending"] = None
            continue
        if s["pending"] != sig:
            s["pending"] = sig
            continue
        s["mtime"], s["size"], s["pending"] = st.st_mtime, st.st_size, None
        try:
            _adopt(media_id, s)
        except Exception:
            pass


def _loop() -> None:
    global _thread
    while True:
        time.sleep(POLL_S)
        try:
            _tick()
        finally:
            reset_thread_conn()
        with _lock:
            if not _sessions:
                _thread = None
                return


def _ensure_thread() -> None:
    global _thread
    with _lock:
        if _thread is None:
            _thread = threading.Thread(target=_loop, name="DAM-edit-with", daemon=True)
            _thread.start()
