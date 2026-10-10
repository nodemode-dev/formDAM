import io
import json
import os
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..db import ex, q1
from ..dedup.visual import ffmpeg_path
from ..services import decode, editsvc, libraryfs, thumbs
from .guard import ensure_visible
from .render import clear_cached, source_of

router = APIRouter()

MAX_STATE = 200_000
PASTE_KEYS = ("light", "color", "detail", "bw", "filter", "levels", "curves")
_base_lock = threading.Lock()
_bases: "OrderedDict[tuple, Any]" = OrderedDict()


class EditIn(BaseModel):
    state: Dict[str, Any]


class BatchEditIn(BaseModel):
    ids: List[int] = Field(..., max_length=20000)
    state: Dict[str, Any]


class PreviewIn(BaseModel):
    state: Dict[str, Any] = {}
    w: int = Field(1600, ge=64, le=4096)
    stages: Optional[List[str]] = None


class TrimIn(BaseModel):
    trim_in: Optional[float] = Field(None, ge=0)
    trim_out: Optional[float] = Field(None, ge=0)


def _row(media_id: int, request: Request):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    return row


def _clean(state: Dict[str, Any]) -> Dict[str, Any]:
    raw = json.dumps(state)
    if len(raw) > MAX_STATE:
        raise HTTPException(413, detail="The edit is too large")
    return {k: v for k, v in state.items() if v not in (None, {}, [])}


def invalidate(media_id: int) -> None:
    clear_cached(media_id)
    for size in thumbs.SIZES:
        try:
            os.unlink(thumbs.thumb_path(media_id, size))
        except OSError:
            pass
    with _base_lock:
        for key in [k for k in _bases if k[0] == media_id]:
            _bases.pop(key, None)
    try:
        from ..services import clipsvc

        clipsvc.forget(media_id)
    except Exception:
        pass


def _store(media_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
    clean = _clean(state)
    if clean:
        ex("UPDATE media SET edit_json=?, edited_ts=?, xmp_ts=NULL WHERE id=?", (json.dumps(clean), time.time(), media_id))
    else:
        ex("UPDATE media SET edit_json=NULL, edited_ts=NULL, xmp_ts=NULL WHERE id=?", (media_id,))
    invalidate(media_id)
    row = q1("SELECT edit_json, edited_ts FROM media WHERE id=?", (media_id,))
    return {"id": media_id, "edit_json": row["edit_json"], "edited_ts": row["edited_ts"]}


@router.get("/media/{media_id}/edits")
def get_edits(media_id: int, request: Request):
    _row(media_id, request)
    return {"state": editsvc.edits_of(media_id), "filters": list(editsvc.FILTERS)}


@router.put("/media/{media_id}/edits")
def put_edits(media_id: int, body: EditIn, request: Request):
    row = _row(media_id, request)
    if row["kind"] != "image":
        raise HTTPException(415, detail="Videos are trimmed, not edited")
    return _store(media_id, body.state)


@router.delete("/media/{media_id}/edits")
def revert_edits(media_id: int, request: Request):
    _row(media_id, request)
    return _store(media_id, {})


@router.post("/media/batch/edits")
def paste_edits(body: BatchEditIn):
    adjustments = {k: v for k, v in body.state.items() if k in PASTE_KEYS}
    out = []
    for media_id in body.ids:
        row = q1("SELECT kind FROM media WHERE id=?", (media_id,))
        if row is None or row["kind"] != "image":
            continue
        current = editsvc.edits_of(media_id)
        for key in PASTE_KEYS:
            current.pop(key, None)
        current.update(adjustments)
        out.append(_store(media_id, current))
    return {"items": out}


def _base(row, width: int):
    key = (row["id"], width, row["edited_ts"] or 0)
    with _base_lock:
        hit = _bases.get(key)
        if hit is not None:
            _bases.move_to_end(key)
            return hit
    src, _ = source_of(row)
    if src is None:
        return None
    img = decode.open_image(src, row["name"], max_long=width, develop=True)
    if img is None:
        return None
    with _base_lock:
        _bases[key] = img
        while len(_bases) > 4:
            _bases.popitem(last=False)
    return img


@router.post("/media/{media_id}/preview")
def preview(media_id: int, body: PreviewIn, request: Request):
    row = _row(media_id, request)
    if row["kind"] != "image":
        raise HTTPException(415, detail="Only stills preview")
    base = _base(row, body.w)
    if base is None:
        raise HTTPException(404, detail="This file could not be decoded")
    stages = [s for s in (body.stages or editsvc.STAGES) if s in editsvc.STAGES]
    img = editsvc.apply_edits(base.copy(), body.state, stages)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=86)
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/media/{media_id}/auto")
def auto(media_id: int, request: Request):
    row = _row(media_id, request)
    base = _base(row, 1024)
    if base is None:
        raise HTTPException(404, detail="This file could not be decoded")
    return {"state": editsvc.auto_enhance(base)}


@router.post("/media/{media_id}/trim")
def set_trim(media_id: int, body: TrimIn, request: Request):
    row = _row(media_id, request)
    if row["kind"] != "video":
        raise HTTPException(415, detail="Only videos trim")
    if body.trim_in is not None and body.trim_out is not None and body.trim_out <= body.trim_in:
        raise HTTPException(400, detail="The end must come after the start")
    ex("UPDATE media SET trim_in=?, trim_out=?, edited_ts=?, xmp_ts=NULL WHERE id=?",
       (body.trim_in, body.trim_out, time.time() if (body.trim_in or body.trim_out) else None, media_id))
    return {"id": media_id, "trim_in": body.trim_in, "trim_out": body.trim_out}


@router.post("/media/{media_id}/trim/export")
def export_trim(media_id: int, request: Request):
    row = _row(media_id, request)
    if row["kind"] != "video" or (row["trim_in"] is None and row["trim_out"] is None):
        raise HTTPException(400, detail="Set a trim first")
    binary = ffmpeg_path()
    if not binary:
        raise HTTPException(409, detail="ffmpeg is not installed")
    src = libraryfs.abs_path(row["rel_path"])
    stem, ext = os.path.splitext(row["name"])
    folder = tempfile.mkdtemp(prefix="dam-trim-")
    out = os.path.join(folder, f"{stem}_trim{ext or '.mov'}")
    start = float(row["trim_in"] or 0)
    cmd = [binary, "-hide_banner", "-loglevel", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src]
    if row["trim_out"]:
        cmd += ["-t", f"{float(row['trim_out']) - start:.3f}"]
    cmd += ["-map", "0", "-map_metadata", "0", "-c", "copy", out]
    done = subprocess.run(cmd, capture_output=True, timeout=600)
    if done.returncode != 0 or not os.path.isfile(out):
        raise HTTPException(500, detail="ffmpeg could not write the clip")
    result = libraryfs.import_one(out, move=True)
    try:
        os.rmdir(folder)
    except OSError:
        pass
    if result.get("status") != "imported":
        raise HTTPException(409, detail="The trimmed clip matches an item already in the library")
    ex("UPDATE media SET created_ts=? WHERE id=?", ((row["created_ts"] or 0) + (row["trim_in"] or 0), result["media_id"]))
    return {"id": result["media_id"]}
