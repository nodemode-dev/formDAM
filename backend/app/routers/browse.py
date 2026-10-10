import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request

from .. import jobs
from ..db import media_dict, q, q1
from ..services import metasvc, query
from .guard import ensure_visible

router = APIRouter()

MEDIA_TYPES = [
    ("video", "Videos"), ("live", "Live Photos"), ("selfie", "Selfies"), ("portrait", "Portrait"),
    ("panorama", "Panoramas"), ("slomo", "Slo-mo"), ("burst", "Bursts"), ("raw", "RAW"),
    ("screenshot", "Screenshots"), ("screen_recording", "Screen Recordings"),
]


def _cursor(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


@router.get("/browse")
def browse(spec: str = Query(""), cursor: str = Query(""), limit: int = Query(400, ge=1, le=1000)):
    result = query.page(query.parse_spec(spec), limit=limit, cursor=_cursor(cursor))
    items = []
    for row in result["rows"]:
        item = media_dict(row)
        item.pop("_sortv", None)
        items.append(item)
    return {"items": items, "next": result["next"]}


@router.get("/browse/count")
def browse_count(spec: str = Query("")):
    return {"count": query.count(query.parse_spec(spec))}


@router.get("/browse/ids")
def browse_ids(spec: str = Query(""), limit: int = Query(20000, ge=1, le=100000)):
    return {"ids": query.ids(query.parse_spec(spec), limit=limit)}


@router.get("/media-types")
def media_types():
    out = []
    for flag, label in MEDIA_TYPES:
        spec = {"rules": [{"field": "flag", "value": flag}], "expand_stacks": True}
        n = query.count(spec)
        cover = query.ids(spec, limit=1)
        out.append({"key": flag, "label": label, "count": n, "cover": cover[0] if cover else None})
    return {"types": out}


@router.get("/imports")
def imports(limit: int = Query(200, ge=1, le=1000)):
    out = []
    for row in q("SELECT * FROM import_batches WHERE imported > 0 ORDER BY started_ts DESC LIMIT ?", (limit,)):
        spec = {"rules": [{"field": "batch", "value": row["id"]}], "sort": "added", "expand_stacks": True}
        n = query.count(spec)
        if n == 0:
            continue
        out.append({"id": row["id"], "started_ts": row["started_ts"], "source": row["source"], "label": row["label"],
                    "count": n, "covers": query.ids(spec, limit=4)})
    return {"batches": out}


@router.get("/media/{media_id}/details")
def details(media_id: int, request: Request):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    item = media_dict(row)
    try:
        item["exif"] = json.loads(row["exif_json"]) if row["exif_json"] else {}
    except ValueError:
        item["exif"] = {}
    try:
        item["iptc"] = json.loads(row["iptc_json"]) if row["iptc_json"] else {}
    except ValueError:
        item["iptc"] = {}
    item["albums"] = [dict(r) for r in q(
        "SELECT al.id, al.name FROM album_items ai JOIN albums al ON al.id=ai.album_id WHERE ai.media_id=?", (media_id,))]
    item["keywords"] = [dict(r) for r in q(
        "SELECT k.id, k.name FROM media_keywords mk JOIN keywords k ON k.id=mk.keyword_id WHERE mk.media_id=? ORDER BY k.name", (media_id,))]
    item["people"] = [dict(r) for r in q(
        """SELECT DISTINCT p.id, p.name FROM faces f JOIN people p ON p.id=f.person_id
           WHERE f.media_id=? AND p.hidden=0""", (media_id,))]
    item["subjects"] = [dict(r) for r in q(
        "SELECT label, kind, score FROM media_labels WHERE media_id=? ORDER BY score DESC LIMIT 12", (media_id,))]
    batch = q1("SELECT id, source, label, started_ts FROM import_batches WHERE id=?", (row["batch_id"],)) if row["batch_id"] else None
    item["batch"] = dict(batch) if batch else None
    return item


@router.get("/metadata/status")
def metadata_status():
    return {"pending": metasvc.pending(), "job": jobs.running("metadata")}


@router.post("/metadata/rescan", status_code=202)
def metadata_rescan(force: bool = Query(False)):
    from ..db import ex

    active = jobs.running("metadata")
    if active:
        return {"job_id": active["id"]}
    if force:
        ex("UPDATE media SET meta_ver=0")
    return {"job_id": jobs.start("metadata", metasvc.backfill_job)}


def ensure_backfill() -> None:
    if metasvc.pending() and not jobs.running("metadata"):
        jobs.start("metadata", metasvc.backfill_job)
