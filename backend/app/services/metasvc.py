import json
import os
from typing import Any, Callable, Dict, List, Optional

from ..db import ex, q, q1
from . import exifmeta, libraryfs

META_VER = 1
RAW_EXTS = {
    "dng", "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf", "rw2", "rwl", "pef",
    "srw", "x3f", "3fr", "iiq", "erf", "kdc", "dcr", "mos", "mrw", "raw",
}
PANORAMA_RATIO = 2.4
SLOMO_FPS = 100.0

_after_apply: List[Callable[[int, Dict[str, Any]], None]] = []


def on_applied(hook: Callable[[int, Dict[str, Any]], None]) -> None:
    if hook not in _after_apply:
        _after_apply.append(hook)


def _is_raw(name: str) -> bool:
    return os.path.splitext(name)[1].lstrip(".").lower() in RAW_EXTS


def read(path: str, kind: str) -> Dict[str, Any]:
    return exifmeta.read_image(path) if kind == "image" else exifmeta.read_video(path)


def _dims(path: str) -> Optional[tuple]:
    from . import decode

    return decode.image_size(path, path)


def apply(media_id: int, meta: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    if row is None:
        return None
    path = libraryfs.abs_path(row["rel_path"])
    if not os.path.isfile(path):
        return None
    if meta is None:
        meta = read(path, row["kind"])
    width, height = row["width"], row["height"]
    if row["kind"] == "image" and (not (width and height) or (_is_raw(row["name"]) and META_VER > (row["meta_ver"] or 0))):
        size = _dims(path)
        if size:
            width, height = size
    created_ts, created_src = row["created_ts"], row["created_src"]
    captured = meta.get("captured_ts")
    if captured and created_src != "exif" and created_src != "adjusted":
        created_ts, created_src = float(captured), "exif"
    is_raw = 1 if _is_raw(row["name"]) else 0
    pano = 1 if row["kind"] == "image" and width and height and max(width, height) / max(1, min(width, height)) >= PANORAMA_RATIO else 0
    lens = (meta.get("lens") or "").lower()
    selfie = 1 if meta.get("camera_type") == "Front" or "front camera" in lens else 0
    portrait = 1 if meta.get("capture_type") == "Portrait" else 0
    slomo = 1 if row["kind"] == "video" and (meta.get("fps") or 0) >= SLOMO_FPS else 0
    lat, lon = meta.get("lat"), meta.get("lon")
    if lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat = lon = None
    keep_location = row["lat"] is not None and row["meta_ver"] and row["meta_ver"] >= META_VER
    ex(
        """UPDATE media SET width=?, height=?, created_ts=?, created_src=?, make=?, model=?, lens=?, focal=?, focal35=?,
           aperture=?, shutter=?, iso=?, flash=?, orientation=?, lat=?, lon=?, alt=?, content_id=?, burst_id=?,
           camera_type=?, capture_type=?, fps=?, is_raw=?, is_panorama=?, is_selfie=?, is_portrait=?, is_slomo=?,
           exif_json=?, meta_ver=? WHERE id=?""",
        (
            width, height, created_ts, created_src, meta.get("make"), meta.get("model"), meta.get("lens"),
            meta.get("focal"), meta.get("focal35"), meta.get("aperture"), meta.get("shutter"), meta.get("iso"),
            meta.get("flash"), meta.get("orientation"),
            row["lat"] if keep_location else lat, row["lon"] if keep_location else lon,
            row["alt"] if keep_location else meta.get("alt"),
            meta.get("content_id") or None, meta.get("burst_id") or None, meta.get("camera_type"),
            meta.get("capture_type"), meta.get("fps"), is_raw, pano, selfie, portrait, slomo,
            json.dumps(meta.get("all") or {}) if meta.get("all") else None, META_VER, media_id,
        ),
    )
    if meta.get("content_id"):
        pair_live(media_id, meta["content_id"], row["kind"])
    for hook in list(_after_apply):
        try:
            hook(media_id, meta)
        except Exception:
            pass
    return meta


def pair_live(media_id: int, content_id: str, kind: str) -> bool:
    other_kind = "video" if kind == "image" else "image"
    other = q1(
        "SELECT id FROM media WHERE content_id=? AND kind=? AND id<>? AND trashed_ts IS NULL ORDER BY id LIMIT 1",
        (content_id, other_kind, media_id),
    )
    if other is None:
        return False
    photo, video = (media_id, other["id"]) if kind == "image" else (other["id"], media_id)
    return libraryfs.link_live(photo, video)


def backfill_job(state: Dict[str, Any]) -> None:
    from .. import vaultcrypt

    rows = q("SELECT id FROM media WHERE meta_ver < ? ORDER BY id", (META_VER,))
    counts = {"pending": len(rows), "read": 0, "skipped": 0}
    state["counts"] = counts
    for row in rows:
        if vaultcrypt.is_vaulted(row["id"]):
            counts["skipped"] += 1
            continue
        try:
            if apply(row["id"]) is None:
                counts["skipped"] += 1
            else:
                counts["read"] += 1
        except Exception:
            counts["skipped"] += 1


def pending() -> int:
    return q1("SELECT COUNT(*) AS n FROM media WHERE meta_ver < ?", (META_VER,))["n"]
