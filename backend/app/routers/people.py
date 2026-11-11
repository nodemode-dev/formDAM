
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import jobs
from ..db import ex, exn, media_dict, q, q1
from ..services import facesvc
from .guard import ensure_visible
from .revalidate import NO_STORE, must_not_store, revalidated_file

router = APIRouter()


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("/people/status")
def people_status():
    info = facesvc.status()
    pending = q1("SELECT COUNT(*) AS n FROM media WHERE face_state=0 AND trashed_ts IS NULL")["n"]
    info["pending_media"] = pending
    active = jobs.running("faces")
    info["job"] = active
    return info


@router.post("/people/scan", status_code=202)
def people_scan():
    info = facesvc.status()
    if not info["ready"]:
        raise HTTPException(409, detail="Face engine not ready: run the installer to fetch the models")
    active = jobs.running("faces")
    if active:
        return {"job_id": active["id"]}
    return {"job_id": jobs.start("faces", facesvc.scan_job)}


class MergeIn(BaseModel):
    into_id: int
    from_ids: List[int]


class HideIn(BaseModel):
    hidden: bool


@router.post("/people/merge")
def merge(body: MergeIn):
    if q1("SELECT id FROM people WHERE id=?", (body.into_id,)) is None:
        raise HTTPException(404, detail="Target person not found")
    moved = facesvc.merge_people(body.into_id, body.from_ids)
    return {"moved_faces": moved}


@router.patch("/people/{person_id}/hidden")
def set_person_hidden(person_id: int, body: HideIn):
    if q1("SELECT id FROM people WHERE id=?", (person_id,)) is None:
        raise HTTPException(404, detail="No such person")
    ex("UPDATE people SET hidden=? WHERE id=?", (1 if body.hidden else 0, person_id))
    return {"ok": True}


@router.delete("/people/{person_id}")
def remove_person(person_id: int):
    if q1("SELECT id FROM people WHERE id=?", (person_id,)) is None:
        raise HTTPException(404, detail="No such person")
    facesvc.delete_person(person_id)
    return {"ok": True}


@router.get("/people/{person_id}/faces")
def person_faces(person_id: int, limit: int = Query(120, ge=1, le=500)):
    rows = q(
        """SELECT f.id, f.media_id, f.quality, f.w, f.h FROM faces f
           JOIN media m ON m.id = f.media_id
           WHERE f.person_id=? AND m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL""",
        (person_id,),
    )
    faces = sorted(rows, key=lambda r: -(r["quality"] * (max(0.0, r["w"] * r["h"]) ** 0.5)))
    return {"faces": [{"id": f["id"], "media_id": f["media_id"], "quality": f["quality"]} for f in faces[:limit]]}


class AssignIn(BaseModel):
    person_id: Optional[int] = None
    new_name: Optional[str] = None


class RebuildIn(BaseModel):
    threshold: Optional[float] = Field(None, ge=0.3, le=0.9)


@router.patch("/faces/{face_id}/person")
def reassign_face(face_id: int, body: AssignIn):
    try:
        pid = facesvc.assign_face(face_id, body.person_id, body.new_name)
    except ValueError:
        raise HTTPException(404, detail="No such face")
    return {"person_id": pid}


@router.post("/people/rebuild")
def rebuild(body: RebuildIn):
    return facesvc.rebuild_people(body.threshold)


@router.get("/people/threshold")
def get_threshold():
    return {"threshold": facesvc.face_threshold()}


@router.delete("/faces/{face_id}/person")
def unassign(face_id: int):
    if q1("SELECT id FROM faces WHERE id=?", (face_id,)) is None:
        raise HTTPException(404, detail="No such face")
    facesvc.unassign_face(face_id)
    return {"ok": True}


class MoveMediaIn(BaseModel):
    media_ids: List[int]
    target_person_id: Optional[int] = None
    new_name: Optional[str] = None


class CoverIn(BaseModel):
    media_id: int


@router.post("/people/{person_id}/cover")
def set_cover(person_id: int, body: CoverIn):
    if q1("SELECT id FROM people WHERE id=?", (person_id,)) is None:
        raise HTTPException(404, detail="No such person")
    face = q1(
        "SELECT id FROM faces WHERE person_id=? AND media_id=? ORDER BY quality DESC LIMIT 1",
        (person_id, body.media_id),
    )
    if face is None:
        raise HTTPException(400, detail="That item has no face of this person")
    ex("UPDATE people SET cover_face_id=?, cover_locked=1 WHERE id=?", (face["id"], person_id))
    return {"ok": True}


@router.delete("/people/{person_id}/cover")
def clear_cover(person_id: int):
    if q1("SELECT id FROM people WHERE id=?", (person_id,)) is None:
        raise HTTPException(404, detail="No such person")
    ex("UPDATE people SET cover_locked=0 WHERE id=?", (person_id,))
    facesvc.refresh_cover(person_id)
    return {"ok": True}


@router.post("/people/{person_id}/reassign-media")
def reassign_media(person_id: int, body: MoveMediaIn):
    if q1("SELECT id FROM people WHERE id=?", (person_id,)) is None:
        raise HTTPException(404, detail="No such person")
    target = body.target_person_id
    if target is None:
        target = ex("INSERT INTO people(name, created_ts) VALUES(?, ?)", (body.new_name, __import__("time").time()))
    elif q1("SELECT id FROM people WHERE id=?", (target,)) is None:
        raise HTTPException(404, detail="No such target person")
    moved = 0
    for mid in body.media_ids:
        moved += exn(
            "UPDATE faces SET person_id=? WHERE person_id=? AND media_id=?",
            (target, person_id, mid),
        )
    remaining = q1("SELECT COUNT(*) AS n FROM faces WHERE person_id=?", (person_id,))
    if remaining["n"] == 0 and q1("SELECT name FROM people WHERE id=?", (person_id,))["name"] is None:
        ex("DELETE FROM people WHERE id=?", (person_id,))
    else:
        facesvc.refresh_cover(person_id)
    facesvc.refresh_cover(target)
    return {"moved_faces": moved, "target_person_id": target}


@router.get("/people")
def list_people(min_faces: int = Query(1, ge=1), include_hidden: bool = Query(False)):
    people = []
    clause = "" if include_hidden else "WHERE hidden=0"
    for row in q(f"SELECT * FROM people {clause} ORDER BY id"):
        stats = q1(
            """SELECT COUNT(*) AS faces, COUNT(DISTINCT f.media_id) AS media
               FROM faces f JOIN media m ON m.id=f.media_id
               WHERE f.person_id=? AND m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL""",
            (row["id"],),
        )
        if stats["faces"] < min_faces:
            continue
        people.append({
            "id": row["id"], "name": row["name"], "faces": stats["faces"],
            "media": stats["media"], "cover_face_id": row["cover_face_id"],
            "hidden": bool(row["hidden"]),
        })
    people.sort(key=lambda p: (-p["media"], p["id"]))
    return {"people": people}


@router.get("/people/{person_id}")
def person_media(person_id: int):
    person = q1("SELECT * FROM people WHERE id=?", (person_id,))
    if person is None:
        raise HTTPException(404, detail="No such person")
    rows = q(
        """SELECT DISTINCT m.* FROM faces f JOIN media m ON m.id=f.media_id
           WHERE f.person_id=? AND m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL
           ORDER BY m.created_ts DESC""",
        (person_id,),
    )
    return {
        "id": person["id"], "name": person["name"], "cover_face_id": person["cover_face_id"],
        "items": [media_dict(r) for r in rows],
    }


@router.patch("/people/{person_id}")
def rename_person(person_id: int, body: RenameIn):
    if q1("SELECT id FROM people WHERE id=?", (person_id,)) is None:
        raise HTTPException(404, detail="No such person")
    ex("UPDATE people SET name=? WHERE id=?", (body.name.strip(), person_id))
    return {"ok": True}


@router.get("/faces/{face_id}/thumb")
def face_thumb(face_id: int, request: Request):
    row = q1("SELECT m.* FROM faces f JOIN media m ON m.id=f.media_id WHERE f.id=?", (face_id,))
    if row is None:
        raise HTTPException(404, detail="Face crop unavailable")
    ensure_visible(row, request)
    path = facesvc.face_crop(face_id)
    if path is None:
        raise HTTPException(404, detail="Face crop unavailable")
    if must_not_store(row):
        with open(path, "rb") as handle:
            return Response(handle.read(), media_type="image/jpeg", headers={"Cache-Control": NO_STORE})
    return revalidated_file(request, path, "image/jpeg")
