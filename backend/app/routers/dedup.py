from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import jobs
from ..db import q1
from ..dedup.visual import DEFAULT_SIMILARITY, FLOOR_SIMILARITY
from ..services import dedupsvc

router = APIRouter()


class ScanIn(BaseModel):
    threshold: int = Field(DEFAULT_SIMILARITY, ge=FLOOR_SIMILARITY, le=100)
    include_videos: bool = True
    auto_resolve_exact: bool = False


class ResolveIn(BaseModel):
    keep_media_id: Optional[int] = None


@router.post("/dedup/scan", status_code=202)
def dedup_scan(body: ScanIn):
    active = jobs.running("dedup")
    if active:
        return {"job_id": active["id"]}
    return {
        "job_id": jobs.start(
            "dedup",
            lambda state: dedupsvc.scan_job(
                state, body.threshold, include_videos=body.include_videos, auto_resolve_exact=body.auto_resolve_exact
            ),
        )
    }


@router.get("/dedup/sets")
def dedup_sets():
    return {"sets": dedupsvc.list_sets(), "floor": FLOOR_SIMILARITY, "default": DEFAULT_SIMILARITY}


@router.post("/dedup/sets/{set_id}/resolve")
def dedup_resolve(set_id: int, body: ResolveIn):
    if q1("SELECT id FROM dup_sets WHERE id=?", (set_id,)) is None:
        raise HTTPException(404, detail="No such duplicate set")
    result = dedupsvc.resolve(set_id, body.keep_media_id)
    if result.get("error"):
        raise HTTPException(409, detail=result["error"])
    return result


@router.post("/dedup/sets/{set_id}/members/{media_id}/trash")
def dedup_trash_member(set_id: int, media_id: int):
    if q1("SELECT id FROM dup_sets WHERE id=?", (set_id,)) is None:
        raise HTTPException(404, detail="No such duplicate set")
    result = dedupsvc.trash_member(set_id, media_id)
    if result.get("error"):
        raise HTTPException(409, detail=result["error"])
    return result


@router.post("/dedup/resolve-exact")
def dedup_resolve_exact():
    return dedupsvc.resolve_all_exact()
