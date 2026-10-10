import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import jobs
from ..config import VERSION, db_path, library_root, models_dir
from ..db import q1, setting_get, setting_set, ex
from ..services import fsbrowse, native_picker, ocrsvc

router = APIRouter()


@router.get("/health")
def health():
    from ..dedup import visual as _visual

    return {
        "ok": True, "version": VERSION, "library": library_root(), "db": db_path(),
        "models": models_dir(), "ffmpeg": bool(_visual.ffmpeg_path()),
    }


@router.get("/fs/roots")
def fs_roots():
    return {"roots": fsbrowse.list_roots()}


@router.get("/fs/browse")
def fs_browse(path: str = Query(min_length=1)):
    try:
        return fsbrowse.list_dirs(path)
    except NotADirectoryError:
        raise HTTPException(404, detail="That path is not a folder")
    except PermissionError as exc:
        raise HTTPException(403, detail=str(exc))


@router.post("/fs/pick")
def fs_pick(initial: str = Query(default="")):
    try:
        picked = native_picker.pick_folder(initial or None)
    except native_picker.PickerBusy as exc:
        raise HTTPException(409, detail=str(exc))
    except native_picker.PickerUnavailable as exc:
        raise HTTPException(501, detail=str(exc))
    return {"path": picked}


class PrefsIn(BaseModel):
    value: dict


@router.get("/prefs/{key}")
def prefs_get(key: str):
    raw = setting_get(f"prefs:{key}")
    return {"key": key, "value": json.loads(raw) if raw else None}


@router.put("/prefs/{key}")
def prefs_put(key: str, body: PrefsIn):
    setting_set(f"prefs:{key}", json.dumps(body.value))
    return {"ok": True}


@router.get("/ocr/status")
def ocr_status():
    info = ocrsvc.status()
    info["job"] = jobs.running("ocr")
    return info


class OcrScanIn(BaseModel):
    force: bool = False


@router.post("/ocr/scan", status_code=202)
def ocr_scan(body: OcrScanIn | None = None):
    if not ocrsvc.engine_name():
        raise HTTPException(409, detail="No text engine: the bundled model is missing & tesseract is not on PATH")
    active = jobs.running("ocr")
    if active:
        return {"job_id": active["id"]}
    if body is not None and body.force:
        ex("UPDATE media SET ocr_text=NULL WHERE trashed_ts IS NULL")
    return {"job_id": jobs.start("ocr", ocrsvc.scan_job)}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    state = jobs.get(job_id)
    if state is None:
        raise HTTPException(404, detail="No such job")
    return {k: v for k, v in state.items() if k != "trace"}


@router.get("/summary")
def summary():
    def count(sql: str) -> int:
        return q1(sql)["n"]

    visible = "trashed_ts IS NULL AND private=0 AND hidden=0 AND live_of IS NULL"
    return {
        "total": count(f"SELECT COUNT(*) AS n FROM media WHERE {visible}"),
        "photos": count(f"SELECT COUNT(*) AS n FROM media WHERE {visible} AND kind='image'"),
        "videos": count(f"SELECT COUNT(*) AS n FROM media WHERE {visible} AND kind='video'"),
        "screenshots": count(f"SELECT COUNT(*) AS n FROM media WHERE {visible} AND is_screenshot=1"),
        "screenrecs": count(f"SELECT COUNT(*) AS n FROM media WHERE {visible} AND is_screen_rec=1"),
        "favorites": count(f"SELECT COUNT(*) AS n FROM media WHERE {visible} AND favorite=1"),
        "recently_viewed": count(f"SELECT COUNT(*) AS n FROM media WHERE {visible} AND viewed_ts IS NOT NULL"),
        "trash": count("SELECT COUNT(*) AS n FROM media WHERE trashed_ts IS NOT NULL"),
        "hidden": count("SELECT COUNT(*) AS n FROM media WHERE hidden=1 AND trashed_ts IS NULL"),
        "albums": count("SELECT COUNT(*) AS n FROM albums"),
        "people": count(
            """SELECT COUNT(*) AS n FROM people p WHERE EXISTS(
                 SELECT 1 FROM faces f JOIN media m ON m.id=f.media_id
                 WHERE f.person_id=p.id AND m.trashed_ts IS NULL AND m.private=0 AND m.live_of IS NULL)"""
        ),
        "dup_sets": count("SELECT COUNT(*) AS n FROM dup_sets WHERE resolved_ts IS NULL"),
    }
