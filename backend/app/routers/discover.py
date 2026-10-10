from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import jobs
from ..db import ex, q, q1
from ..services import clipsvc, query

router = APIRouter()

VISIBLE = "m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL"


class PetIn(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    hidden: Optional[bool] = None


class PetMergeIn(BaseModel):
    into_id: int
    from_ids: List[int]


def ensure_clip() -> None:
    try:
        info = clipsvc.status()
    except Exception:
        return
    if info["ready"] and info["pending"] and not jobs.running("clip"):
        jobs.start("clip", clipsvc.index_job)


@router.get("/clip/status")
def clip_status():
    info = clipsvc.status()
    job = jobs.running("clip")
    return {**info, "job": job}


@router.post("/clip/index", status_code=202)
def clip_index():
    info = clipsvc.status()
    if not info["ready"]:
        raise HTTPException(409, detail="The visual search model is not installed; run the installer again to fetch it")
    running = jobs.running("clip")
    if running:
        return {"job_id": running["id"]}
    return {"job_id": jobs.start("clip", clipsvc.index_job)}


def _cover(sql: str, params) -> Optional[int]:
    row = q1(f"SELECT m.id FROM media m WHERE {VISIBLE} AND {sql} ORDER BY m.favorite DESC, m.rating DESC, m.created_ts DESC LIMIT 1", params)
    return row["id"] if row else None


@router.get("/labels")
def labels(kind: str = Query("subject", pattern="^(subject|content)$")):
    rows = q(f"""SELECT l.label, COUNT(*) AS n FROM media_labels l JOIN media m ON m.id=l.media_id
                 WHERE l.kind=? AND {VISIBLE} GROUP BY l.label ORDER BY n DESC""", (kind,))
    return {"labels": [{"label": r["label"], "count": r["n"],
                        "cover": _cover("m.id IN (SELECT media_id FROM media_labels WHERE label=?)", (r["label"],))} for r in rows]}


@router.get("/pets")
def pets():
    out = []
    for pet in q("SELECT id, name, species, cover_media_id, hidden FROM pets ORDER BY members DESC, id"):
        count = q1(f"SELECT COUNT(*) AS n FROM media m WHERE m.pet_id=? AND {VISIBLE}", (pet["id"],))["n"]
        if count == 0:
            continue
        out.append({"id": pet["id"], "name": pet["name"], "species": pet["species"], "count": count,
                    "cover": _cover("m.pet_id=?", (pet["id"],)), "hidden": bool(pet["hidden"])})
    return {"pets": out}


@router.patch("/pets/{pet_id}")
def update_pet(pet_id: int, body: PetIn):
    if q1("SELECT id FROM pets WHERE id=?", (pet_id,)) is None:
        raise HTTPException(404, detail="No such pet")
    if body.name is not None:
        ex("UPDATE pets SET name=? WHERE id=?", (body.name.strip() or None, pet_id))
    if body.hidden is not None:
        ex("UPDATE pets SET hidden=? WHERE id=?", (1 if body.hidden else 0, pet_id))
    return {"ok": True}


@router.post("/pets/merge")
def merge_pets(body: PetMergeIn):
    if q1("SELECT id FROM pets WHERE id=?", (body.into_id,)) is None:
        raise HTTPException(404, detail="No such pet")
    for pid in body.from_ids:
        if pid == body.into_id:
            continue
        ex("UPDATE media SET pet_id=? WHERE pet_id=?", (body.into_id, pid))
        ex("DELETE FROM pets WHERE id=?", (pid,))
    total = q1("SELECT COUNT(*) AS n FROM media WHERE pet_id=?", (body.into_id,))["n"]
    ex("UPDATE pets SET members=? WHERE id=?", (total, body.into_id))
    return {"ok": True, "count": total}


@router.post("/media/{media_id}/not-pet")
def not_pet(media_id: int):
    ex("UPDATE media SET pet_id=NULL WHERE id=?", (media_id,))
    return {"ok": True}


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/search/suggest")
def suggest(text: str = Query("", max_length=200)):
    needle = text.strip()
    if not needle:
        return {"groups": []}
    like = _like(needle)
    groups = []
    people = q("""SELECT p.id, p.name, COUNT(DISTINCT f.media_id) AS n FROM people p JOIN faces f ON f.person_id=p.id
                  WHERE p.name LIKE ? ESCAPE '\\' AND p.hidden=0 GROUP BY p.id ORDER BY n DESC LIMIT 6""", (like,))
    if people:
        groups.append({"kind": "person", "title": "People", "items": [
            {"label": r["name"], "count": r["n"], "rule": {"field": "person", "value": r["id"]}} for r in people]})
    places = q(f"""SELECT COALESCE(m.place, m.country) AS label, COUNT(*) AS n FROM media m WHERE {VISIBLE}
                   AND (m.place LIKE ? ESCAPE '\\' OR m.country LIKE ? ESCAPE '\\' OR m.admin LIKE ? ESCAPE '\\')
                   GROUP BY label ORDER BY n DESC LIMIT 6""", (like, like, like))
    if places:
        groups.append({"kind": "place", "title": "Places", "items": [
            {"label": r["label"], "count": r["n"], "rule": {"field": "place", "op": "contains", "value": r["label"]}} for r in places]})
    keywords = q("""SELECT k.id, k.name, COUNT(mk.media_id) AS n FROM keywords k JOIN media_keywords mk ON mk.keyword_id=k.id
                    WHERE k.name LIKE ? ESCAPE '\\' GROUP BY k.id ORDER BY n DESC LIMIT 6""", (like,))
    if keywords:
        groups.append({"kind": "keyword", "title": "Keywords", "items": [
            {"label": r["name"], "count": r["n"], "rule": {"field": "keyword", "value": r["id"]}} for r in keywords]})
    subjects = q(f"""SELECT l.label, l.kind, COUNT(*) AS n FROM media_labels l JOIN media m ON m.id=l.media_id
                     WHERE l.label LIKE ? ESCAPE '\\' AND {VISIBLE} GROUP BY l.label ORDER BY n DESC LIMIT 6""", (like,))
    if subjects:
        groups.append({"kind": "subject", "title": "Subjects & Content", "items": [
            {"label": r["label"].title(), "count": r["n"], "rule": {"field": "subject", "value": r["label"]}} for r in subjects]})
    pets_ = q("SELECT id, name FROM pets WHERE name LIKE ? ESCAPE '\\' AND hidden=0 LIMIT 4", (like,))
    if pets_:
        groups.append({"kind": "pet", "title": "Pets", "items": [
            {"label": r["name"], "count": None, "rule": {"field": "pet", "value": r["id"]}} for r in pets_]})
    albums = q("""SELECT a.id, a.name FROM albums a WHERE a.is_private=0 AND a.name LIKE ? ESCAPE '\\' LIMIT 4""", (like,))
    if albums:
        groups.append({"kind": "album", "title": "Albums", "items": [
            {"label": r["name"], "count": None, "rule": {"field": "album", "value": r["id"]}} for r in albums]})
    span = query.parse_date_range(needle)
    if span is not None:
        n = query.count({"rules": [{"field": "date", "value": needle}]})
        groups.append({"kind": "date", "title": "Dates", "items": [{"label": needle, "count": n, "rule": {"field": "date", "value": needle}}]})
    if clipsvc.ready() and len(needle) > 2:
        found = clipsvc.search(needle)
        if found:
            groups.append({"kind": "visual", "title": "Looks Like", "items": [
                {"label": needle, "count": len(found), "rule": {"field": "visual", "value": needle}}]})
    return {"groups": groups}
