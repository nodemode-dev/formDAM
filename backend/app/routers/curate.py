import json
import mimetypes
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import jobs
from ..db import ex, q1
from ..services import curatesvc

router = APIRouter()

THEMES = ("gentle", "uplifting", "dreamy", "none")
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".aiff", ".aif", ".flac", ".ogg"}


class GroupIn(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    hidden: Optional[bool] = None


class MemoryIn(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    subtitle: Optional[str] = Field(None, max_length=200)
    favorite: Optional[bool] = None
    hidden: Optional[bool] = None
    theme: Optional[str] = None
    music_path: Optional[str] = Field(None, max_length=2000)
    key_media_id: Optional[int] = None


class CustomIn(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=500)
    title: str = Field("My Memory", max_length=200)


class RemoveIn(BaseModel):
    ids: List[int]


@router.get("/people/groups")
def people_groups():
    return {"groups": curatesvc.groups()}


@router.patch("/people/groups/{key}")
def update_group(key: str, body: GroupIn):
    if not all(part.isdigit() for part in key.split("-")):
        raise HTTPException(400, detail="Bad group key")
    ex("INSERT OR IGNORE INTO people_groups(key) VALUES(?)", (key,))
    if body.name is not None:
        ex("UPDATE people_groups SET name=? WHERE key=?", (body.name.strip() or None, key))
    if body.hidden is not None:
        ex("UPDATE people_groups SET hidden=? WHERE key=?", (1 if body.hidden else 0, key))
    return {"ok": True}


def ensure_memories() -> None:
    if not jobs.running("memories"):
        jobs.start("memories", curatesvc.generate)


@router.get("/memories")
def memories():
    return {"memories": curatesvc.listing()}


@router.post("/memories/generate", status_code=202)
def generate():
    running = jobs.running("memories")
    return {"job_id": running["id"] if running else jobs.start("memories", curatesvc.generate)}


@router.post("/memories", status_code=201)
def create_memory(body: CustomIn):
    return {"id": curatesvc.custom(body.ids, body.title.strip() or "My Memory")}


@router.get("/memories/{memory_id}")
def memory(memory_id: int):
    row = q1("SELECT * FROM memories WHERE id=?", (memory_id,))
    if row is None:
        raise HTTPException(404, detail="No such memory")
    out = dict(row)
    out["music"] = json.loads(row["music"]) if row["music"] else {"theme": "gentle"}
    out["ids"] = curatesvc.items(memory_id)
    return out


@router.patch("/memories/{memory_id}")
def update_memory(memory_id: int, body: MemoryIn):
    row = q1("SELECT music FROM memories WHERE id=?", (memory_id,))
    if row is None:
        raise HTTPException(404, detail="No such memory")
    if body.title is not None:
        ex("UPDATE memories SET title=? WHERE id=?", (body.title.strip() or "Memory", memory_id))
    if body.subtitle is not None:
        ex("UPDATE memories SET subtitle=? WHERE id=?", (body.subtitle, memory_id))
    if body.favorite is not None:
        ex("UPDATE memories SET favorite=? WHERE id=?", (1 if body.favorite else 0, memory_id))
    if body.hidden is not None:
        ex("UPDATE memories SET hidden=? WHERE id=?", (1 if body.hidden else 0, memory_id))
    if body.key_media_id is not None:
        ex("UPDATE memories SET key_media_id=? WHERE id=?", (body.key_media_id, memory_id))
    if body.theme is not None or body.music_path is not None:
        music = json.loads(row["music"]) if row["music"] else {"theme": "gentle"}
        if body.theme is not None:
            if body.theme not in THEMES:
                raise HTTPException(400, detail="Unknown music theme")
            music["theme"] = body.theme
            music.pop("path", None)
        if body.music_path:
            path = os.path.abspath(os.path.expanduser(body.music_path))
            if not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in AUDIO_EXTS:
                raise HTTPException(400, detail="Choose an audio file (mp3, m4a, aac, wav, aiff, flac or ogg)")
            music = {"theme": "file", "path": path}
        ex("UPDATE memories SET music=? WHERE id=?", (json.dumps(music), memory_id))
    return {"ok": True}


@router.post("/memories/{memory_id}/remove")
def remove_from_memory(memory_id: int, body: RemoveIn):
    for media_id in body.ids:
        ex("DELETE FROM memory_items WHERE memory_id=? AND media_id=?", (memory_id, media_id))
    return {"ok": True}


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int):
    ex("UPDATE memories SET hidden=1 WHERE id=?", (memory_id,))
    return {"ok": True}


@router.get("/memories/{memory_id}/music")
def memory_music(memory_id: int):
    row = q1("SELECT music FROM memories WHERE id=?", (memory_id,))
    music = json.loads(row["music"]) if row and row["music"] else {}
    path = music.get("path")
    if not path or not os.path.isfile(path):
        raise HTTPException(404, detail="No music file")
    return FileResponse(path, media_type=mimetypes.guess_type(path)[0] or "audio/mpeg", headers={"Cache-Control": "no-store"})
