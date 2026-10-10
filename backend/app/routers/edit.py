import io
import json
import os
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..db import ex, q1
from ..dedup.visual import ffmpeg_path
from ..services import cleanup, decode, editsvc, extedit, libraryfs, thumbs
from .guard import ensure_visible
from .render import clear_cached, source_of

router = APIRouter()

MAX_STATE = 200_000
PASTE_KEYS = ("light", "color", "detail", "bw", "filter", "levels", "curves", "raw", "lens")
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


class EditWithIn(BaseModel):
    app: Optional[str] = Field(None, max_length=200)


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
    ex("UPDATE media SET is_long_exposure=? WHERE id=?", (1 if clean.get("effect") == "long_exposure" else 0, media_id))
    invalidate(media_id)
    row = q1("SELECT edit_json, edited_ts FROM media WHERE id=?", (media_id,))
    return {"id": media_id, "edit_json": row["edit_json"], "edited_ts": row["edited_ts"]}


@router.get("/media/{media_id}/edits")
def get_edits(media_id: int, request: Request):
    _row(media_id, request)
    cleanup.warm()
    return {"state": editsvc.edits_of(media_id), "filters": list(editsvc.FILTERS), "cleanup": cleanup.ready()}


@router.put("/media/{media_id}/edits")
def put_edits(media_id: int, body: EditIn, request: Request):
    row = _row(media_id, request)
    if row["kind"] != "image":
        raise HTTPException(415, detail="Videos are trimmed, not edited")
    return _store(media_id, body.state)


@router.delete("/media/{media_id}/edits")
def revert_edits(media_id: int, request: Request):
    _row(media_id, request)
    external = extedit.external_path(editsvc.edits_of(media_id))
    out = _store(media_id, {})
    if external:
        try:
            os.unlink(external)
        except OSError:
            pass
    return out


@router.post("/media/{media_id}/edit-with")
def edit_with(media_id: int, body: EditWithIn, request: Request):
    row = _row(media_id, request)
    from .. import vaultcrypt

    if vaultcrypt.protected(row) or vaultcrypt.is_vaulted(media_id):
        raise HTTPException(409, detail="Protected items stay inside the vault")
    if row["kind"] != "image":
        raise HTTPException(415, detail="Only photos round-trip to another app")
    if not os.path.isfile(libraryfs.abs_path(row["rel_path"])):
        raise HTTPException(404, detail="Original file missing on disk")
    try:
        return extedit.start(media_id, body.app, _store)
    except (OSError, ValueError) as exc:
        raise HTTPException(422, detail=str(exc))


@router.get("/media/{media_id}/edit-with")
def edit_with_status(media_id: int, request: Request):
    _row(media_id, request)
    row = q1("SELECT edit_json, edited_ts FROM media WHERE id=?", (media_id,))
    return {**extedit.status(media_id), "edit_json": row["edit_json"], "edited_ts": row["edited_ts"]}


@router.delete("/media/{media_id}/edit-with")
def edit_with_stop(media_id: int, request: Request):
    _row(media_id, request)
    extedit.stop(media_id)
    return {"ok": True}


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


def _base(row, width: int, raw_opts: Optional[Dict[str, Any]] = None, external: Optional[str] = None):
    raw_opts = raw_opts if decode.is_raw(row["name"]) and raw_opts and not external else None
    key = (row["id"], width, row["edited_ts"] or 0, json.dumps(raw_opts, sort_keys=True) if raw_opts else "", external or "")
    with _base_lock:
        hit = _bases.get(key)
        if hit is not None:
            _bases.move_to_end(key)
            return hit
    src, _ = (external, False) if external else source_of(row)
    if src is None:
        return None
    img = decode.open_image(src, os.path.basename(external) if external else row["name"], max_long=width, develop=True, raw_opts=raw_opts)
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
    base = editsvc.long_exposure(media_id, body.w) if body.state.get("effect") == "long_exposure" else None
    base = base if base is not None else _base(row, body.w, body.state.get("raw"), extedit.external_path(body.state))
    if base is None:
        raise HTTPException(404, detail="This file could not be decoded")
    stages = [s for s in (body.stages or editsvc.STAGES) if s in editsvc.STAGES]
    img = editsvc.apply_edits(base.copy(), body.state, stages)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=86)
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


class SegmentIn(BaseModel):
    x: Optional[float] = Field(None, ge=0, le=1)
    y: Optional[float] = Field(None, ge=0, le=1)
    box: Optional[List[Annotated[float, Field(ge=0, le=1)]]] = Field(None, min_length=4, max_length=4)


_analysis: "OrderedDict[tuple, Any]" = OrderedDict()
_analysis_lock = threading.Lock()


def _analysis_base(row):
    import numpy as np

    base = _base(row, 1024, None, extedit.external_path(editsvc.edits_of(row["id"])))
    if base is None:
        raise HTTPException(404, detail="This file could not be decoded")
    return np.asarray(base.convert("RGB"))


def _analyse(row, kind: str):
    from ..services import cleanmodels

    key = (row["id"], kind, extedit.external_path(editsvc.edits_of(row["id"])) or "", row["sha256"])
    with _analysis_lock:
        hit = _analysis.get(key)
    if hit is not None:
        return hit
    rgb = _analysis_base(row)
    value = cleanmodels.suggest(rgb) if kind == "suggest" else cleanmodels.faces(rgb)
    with _analysis_lock:
        _analysis[key] = value
        while len(_analysis) > 32:
            _analysis.popitem(last=False)
    return value


@router.get("/media/{media_id}/cleanup")
def cleanup_info(media_id: int, request: Request):
    from ..services import cleanmodels

    row = _row(media_id, request)
    if row["kind"] != "image":
        raise HTTPException(415, detail="Clean Up works on photos")
    have = cleanmodels.status()
    return {"fill": cleanup.ready(), **have, "faces_found": _analyse(row, "faces") if have["faces"] else []}


@router.get("/media/{media_id}/cleanup/suggest")
def cleanup_suggest(media_id: int, request: Request):
    from ..services import cleanmodels

    row = _row(media_id, request)
    if not cleanmodels.status()["suggest"]:
        return {"objects": [], "ready": False}
    return {"objects": _analyse(row, "suggest"), "ready": True}


@router.post("/media/{media_id}/cleanup/segment")
def cleanup_segment(media_id: int, body: SegmentIn, request: Request):
    from ..services import cleanmodels

    row = _row(media_id, request)
    if not cleanmodels.status()["segment"]:
        raise HTTPException(409, detail="The object selection model is not installed; brush over the object instead")
    if body.box is None and (body.x is None or body.y is None):
        raise HTTPException(400, detail="Give a point or a box")
    points = [(body.x, body.y)] if body.x is not None and body.y is not None else []
    return cleanmodels.segment(_analysis_base(row), points=points, box=body.box)


@router.get("/media/{media_id}/raw-info")
def raw_info(media_id: int, request: Request):
    row = _row(media_id, request)
    if not decode.is_raw(row["name"]):
        return {"raw": False}
    src, _ = source_of(row)
    if src is None:
        raise HTTPException(404, detail="The original is missing")
    from ..services import rawdev

    try:
        with decode._raw_handle(src) as raw:
            shot = rawdev.as_shot(raw)
    except Exception:
        return {"raw": True, "temp": 5500, "tint": 0, "kelvin": False, "readable": False}
    return {"raw": True, "readable": True, **shot}


@router.get("/media/{media_id}/auto")
def auto(media_id: int, request: Request):
    row = _row(media_id, request)
    base = _base(row, 1024, None, extedit.external_path(editsvc.edits_of(media_id)))
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
