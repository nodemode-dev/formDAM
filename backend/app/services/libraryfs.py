import hashlib
import os
import shutil
import threading
import time
from datetime import datetime
from typing import Any, Dict, List

from ..config import originals_dir
from ..db import ex, q1
from . import classify, mediainfo

HASH_CHUNK = 1 << 20


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(HASH_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def gather_media(root: str) -> List[str]:
    found: List[str] = []
    if os.path.isfile(root):
        kind, _ = classify.media_kind(os.path.basename(root))
        return [root] if kind else []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            if name.startswith("."):
                continue
            kind, _ = classify.media_kind(name)
            if kind:
                found.append(os.path.join(base, name))
    return found


def _dest_for(created_ts: float, name: str) -> str:
    stamp = datetime.fromtimestamp(created_ts)
    folder = os.path.join(originals_dir(), f"{stamp.year:04d}", f"{stamp.month:02d}")
    os.makedirs(folder, exist_ok=True)
    base, extension = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    counter = 1
    while os.path.exists(candidate) or q1("SELECT id FROM media WHERE rel_path=?", (os.path.relpath(candidate, originals_dir()),)):
        candidate = os.path.join(folder, f"{base}-{counter}{extension}")
        counter += 1
    return candidate


def import_one(path: str, move: bool = False) -> Dict[str, Any]:
    name = os.path.basename(path)
    kind, mime = classify.media_kind(name)
    if not kind:
        return {"status": "skipped-kind"}
    size = os.path.getsize(path)
    sha = sha256_of(path)
    existing = q1("SELECT id FROM media WHERE sha256=? AND size=?", (sha, size))
    if existing:
        return {"status": "duplicate", "media_id": existing["id"]}
    width = height = None
    duration = None
    exif_ts = None
    if kind == "image":
        width, height, exif_ts = mediainfo.image_meta(path)
    else:
        width, height, duration, exif_ts = mediainfo.video_meta(path)
    if exif_ts:
        created_ts, created_src = exif_ts, "exif"
    else:
        created_ts, created_src = mediainfo.fs_created(path)
    dest = _dest_for(created_ts, name)
    if move:
        shutil.move(path, dest)
    else:
        shutil.copy2(path, dest)
    rel = os.path.relpath(dest, originals_dir())
    is_screenshot = 1 if kind == "image" and classify.looks_screenshot(name, mime, exif_ts is not None, width, height) else 0
    is_screen_rec = 1 if classify.looks_screen_recording(name, kind) else 0
    media_id = ex(
        """INSERT INTO media(sha256, rel_path, name, size, kind, mime, width, height, duration,
           created_ts, created_src, imported_ts, is_screenshot, is_screen_rec)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sha, rel, os.path.basename(dest), size, kind, mime, width, height, duration,
         created_ts, created_src, time.time(), is_screenshot, is_screen_rec),
    )
    batch_id = getattr(_batch, "id", None)
    if batch_id:
        ex("UPDATE media SET batch_id=? WHERE id=?", (batch_id, media_id))
        ex("UPDATE import_batches SET imported=imported+1 WHERE id=?", (batch_id,))
    try:
        from . import metasvc

        metasvc.apply(media_id)
    except Exception:
        pass
    return {"status": "imported", "media_id": media_id, "id": media_id, "kind": kind, "rel_path": rel}


_batch = threading.local()


def begin_batch(source: str, label: str = "") -> int:
    batch_id = ex("INSERT INTO import_batches(started_ts, source, label) VALUES(?,?,?)", (time.time(), source, label or None))
    _batch.id = batch_id
    return batch_id


def end_batch() -> None:
    batch_id = getattr(_batch, "id", None)
    _batch.id = None
    if batch_id:
        ex("UPDATE import_batches SET finished_ts=? WHERE id=?", (time.time(), batch_id))
        ex("DELETE FROM import_batches WHERE id=? AND imported=0", (batch_id,))


def link_live(photo_id: int, video_id: int) -> bool:
    if not photo_id or not video_id or photo_id == video_id:
        return False
    photo = q1("SELECT id, kind, live_video_id FROM media WHERE id=?", (photo_id,))
    video = q1("SELECT id, kind, live_of FROM media WHERE id=?", (video_id,))
    if not photo or not video or photo["kind"] != "image" or video["kind"] != "video":
        return False
    if photo["live_video_id"] not in (None, video_id) or video["live_of"] not in (None, photo_id):
        return False
    ex("UPDATE media SET live_video_id=? WHERE id=?", (video_id, photo_id))
    ex("UPDATE media SET live_of=? WHERE id=?", (photo_id, video_id))
    return True


def abs_path(rel: str) -> str:
    return os.path.join(originals_dir(), rel)
