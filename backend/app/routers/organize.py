import time
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..db import ex, q, q1
from ..services import keywordsvc, stacksvc
from .guard import ensure_visible

router = APIRouter()

LABELS = {"", "red", "orange", "yellow", "green", "blue", "purple", "gray"}
TEXT_LIMIT = 4000


class MetaIn(BaseModel):
    rating: Optional[int] = Field(None, ge=0, le=5)
    label: Optional[str] = None
    rejected: Optional[bool] = None
    favorite: Optional[bool] = None
    title: Optional[str] = Field(None, max_length=TEXT_LIMIT)
    caption: Optional[str] = Field(None, max_length=TEXT_LIMIT)
    alt_text: Optional[str] = Field(None, max_length=TEXT_LIMIT)


class BatchMetaIn(MetaIn):
    ids: List[int]


def _apply_meta(media_id: int, body: MetaIn) -> Dict[str, Any]:
    sets, params = [], []
    if body.rating is not None:
        sets.append("rating=?")
        params.append(body.rating)
    if body.label is not None:
        label = body.label.strip().lower()
        if label not in LABELS:
            raise HTTPException(422, detail=f"Unknown label {body.label!r}")
        sets.append("label=?")
        params.append(label or None)
    if body.rejected is not None:
        sets.append("rejected=?")
        params.append(1 if body.rejected else 0)
    if body.favorite is not None:
        sets.append("favorite=?")
        params.append(1 if body.favorite else 0)
    for field in ("title", "caption", "alt_text"):
        value = getattr(body, field)
        if value is not None:
            sets.append(f"{field}=?")
            params.append(value.strip() or None)
    if sets:
        sets.append("xmp_ts=NULL")
        ex(f"UPDATE media SET {', '.join(sets)} WHERE id=?", (*params, media_id))
    row = q1("SELECT id, rating, label, rejected, favorite, title, caption, alt_text FROM media WHERE id=?", (media_id,))
    out = dict(row)
    out["favorite"] = bool(out["favorite"])
    return out


@router.patch("/media/{media_id}/meta")
def set_meta(media_id: int, body: MetaIn, request: Request):
    ensure_visible(q1("SELECT * FROM media WHERE id=?", (media_id,)), request)
    return _apply_meta(media_id, body)


@router.post("/media/batch/meta")
def set_meta_batch(body: BatchMetaIn, request: Request):
    out = []
    for media_id in body.ids[:5000]:
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        if row is None:
            continue
        ensure_visible(row, request)
        out.append(_apply_meta(media_id, body))
    return {"items": out}


class KeywordIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: Optional[int] = None


class KeywordPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    parent_id: Optional[int] = None
    detach: bool = False
    shortcut: Optional[str] = Field(None, max_length=1)


class KeywordAssign(BaseModel):
    ids: List[int]
    add: List[Union[int, str]] = []
    remove: List[int] = []


class KeywordMerge(BaseModel):
    into_id: int
    from_ids: List[int]


class KeywordImport(BaseModel):
    text: str
    replace: bool = False


@router.get("/keywords")
def list_keywords():
    return {"keywords": keywordsvc.tree()}


@router.post("/keywords", status_code=201)
def create_keyword(body: KeywordIn):
    return keywordsvc.ensure(body.name, body.parent_id)


@router.patch("/keywords/{keyword_id}")
def patch_keyword(keyword_id: int, body: KeywordPatch):
    try:
        return keywordsvc.update(keyword_id, body.name, body.parent_id, body.detach, body.shortcut)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.delete("/keywords/{keyword_id}")
def delete_keyword(keyword_id: int):
    return {"removed": keywordsvc.delete(keyword_id)}


@router.post("/keywords/merge")
def merge_keywords(body: KeywordMerge):
    return {"moved": keywordsvc.merge(body.into_id, body.from_ids)}


@router.post("/media/keywords")
def assign_keywords(body: KeywordAssign, request: Request):
    for media_id in body.ids:
        ensure_visible(q1("SELECT * FROM media WHERE id=?", (media_id,)), request)
    return keywordsvc.assign(body.ids, body.add, body.remove)


@router.get("/keywords/export", response_class=PlainTextResponse)
def export_keywords():
    return keywordsvc.export_text()


@router.post("/keywords/import")
def import_keywords(body: KeywordImport):
    return {"created": keywordsvc.import_text(body.text, body.replace)}


class StackIn(BaseModel):
    ids: List[int]
    top_id: Optional[int] = None


class TopIn(BaseModel):
    media_id: int


@router.post("/stacks", status_code=201)
def make_stack(body: StackIn):
    if len(body.ids) < 2:
        raise HTTPException(422, detail="A stack needs at least two items")
    return {"stack_id": stacksvc.create(body.ids, body.top_id, "manual")}


@router.get("/stacks/{stack_id}")
def stack_members(stack_id: int):
    stack = q1("SELECT * FROM stacks WHERE id=?", (stack_id,))
    if stack is None:
        raise HTTPException(404, detail="No such stack")
    from ..db import media_dict
    rows = q("""SELECT * FROM media WHERE stack_id=? AND trashed_ts IS NULL AND hidden=0 AND private=0
               ORDER BY created_ts, id""", (stack_id,))
    return {"id": stack_id, "kind": stack["kind"], "top_media_id": stack["top_media_id"], "items": [media_dict(r) for r in rows]}


@router.post("/stacks/{stack_id}/top")
def set_stack_top(stack_id: int, body: TopIn):
    if q1("SELECT id FROM media WHERE id=? AND stack_id=?", (body.media_id, stack_id)) is None:
        raise HTTPException(404, detail="That item is not in this stack")
    ex("UPDATE stacks SET top_media_id=? WHERE id=?", (body.media_id, stack_id))
    return {"ok": True}


@router.delete("/stacks/{stack_id}")
def unstack(stack_id: int):
    stacksvc.dissolve(stack_id)
    return {"ok": True}


@router.post("/stacks/{stack_id}/remove")
def unstack_items(stack_id: int, body: StackIn):
    stacksvc.remove(stack_id, body.ids)
    return {"ok": True}


@router.post("/stacks/auto")
def auto_stack(window_s: float = 0.0):
    return stacksvc.auto(window_s)


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: Optional[int] = None


class FolderPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    parent_id: Optional[int] = None
    to_root: bool = False
    position: Optional[int] = None


@router.get("/album-folders")
def list_folders():
    return {"folders": [dict(r) for r in q("SELECT * FROM album_folders ORDER BY position, name COLLATE NOCASE")]}


@router.post("/album-folders", status_code=201)
def create_folder(body: FolderIn):
    if body.parent_id is not None and q1("SELECT id FROM album_folders WHERE id=?", (body.parent_id,)) is None:
        raise HTTPException(404, detail="No such parent folder")
    folder_id = ex("INSERT INTO album_folders(name, parent_id, created_ts) VALUES(?,?,?)", (body.name.strip(), body.parent_id, time.time()))
    return dict(q1("SELECT * FROM album_folders WHERE id=?", (folder_id,)))


def _descends(folder_id: int, ancestor: int) -> bool:
    cur: Optional[int] = folder_id
    seen = set()
    while cur is not None and cur not in seen:
        if cur == ancestor:
            return True
        seen.add(cur)
        row = q1("SELECT parent_id FROM album_folders WHERE id=?", (cur,))
        cur = row["parent_id"] if row else None
    return False


@router.patch("/album-folders/{folder_id}")
def patch_folder(folder_id: int, body: FolderPatch):
    if q1("SELECT id FROM album_folders WHERE id=?", (folder_id,)) is None:
        raise HTTPException(404, detail="No such folder")
    if body.name is not None:
        ex("UPDATE album_folders SET name=? WHERE id=?", (body.name.strip(), folder_id))
    if body.to_root:
        ex("UPDATE album_folders SET parent_id=NULL WHERE id=?", (folder_id,))
    elif body.parent_id is not None:
        if _descends(body.parent_id, folder_id):
            raise HTTPException(409, detail="A folder cannot go inside itself")
        ex("UPDATE album_folders SET parent_id=? WHERE id=?", (body.parent_id, folder_id))
    if body.position is not None:
        ex("UPDATE album_folders SET position=? WHERE id=?", (body.position, folder_id))
    return dict(q1("SELECT * FROM album_folders WHERE id=?", (folder_id,)))


@router.delete("/album-folders/{folder_id}")
def delete_folder(folder_id: int):
    row = q1("SELECT * FROM album_folders WHERE id=?", (folder_id,))
    if row is None:
        raise HTTPException(404, detail="No such folder")
    ex("UPDATE albums SET folder_id=? WHERE folder_id=?", (row["parent_id"], folder_id))
    ex("UPDATE album_folders SET parent_id=? WHERE parent_id=?", (row["parent_id"], folder_id))
    ex("DELETE FROM album_folders WHERE id=?", (folder_id,))
    return {"ok": True}


class AlbumFolderIn(BaseModel):
    folder_id: Optional[int] = None


@router.post("/albums/{album_id}/folder")
def move_album(album_id: int, body: AlbumFolderIn):
    if q1("SELECT id FROM albums WHERE id=?", (album_id,)) is None:
        raise HTTPException(404, detail="No such album")
    if body.folder_id is not None and q1("SELECT id FROM album_folders WHERE id=?", (body.folder_id,)) is None:
        raise HTTPException(404, detail="No such folder")
    ex("UPDATE albums SET folder_id=? WHERE id=?", (body.folder_id, album_id))
    return {"ok": True}


class SmartIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rules: List[Dict[str, Any]]
    match: str = "all"
    sort: Optional[str] = None
    folder_id: Optional[int] = None


@router.post("/smart-albums", status_code=201)
def create_smart(body: SmartIn):
    import json

    spec = {"rules": body.rules, "match": "any" if body.match == "any" else "all"}
    if body.sort:
        spec["sort"] = body.sort
    album_id = ex(
        "INSERT INTO albums(name, created_ts, is_private, rules_json, folder_id) VALUES(?,?,0,?,?)",
        (body.name.strip(), time.time(), json.dumps(spec), body.folder_id),
    )
    return {"id": album_id, "name": body.name.strip(), "rules": spec}


@router.put("/smart-albums/{album_id}")
def update_smart(album_id: int, body: SmartIn):
    import json

    if q1("SELECT id FROM albums WHERE id=? AND rules_json IS NOT NULL", (album_id,)) is None:
        raise HTTPException(404, detail="No such smart album")
    spec = {"rules": body.rules, "match": "any" if body.match == "any" else "all"}
    if body.sort:
        spec["sort"] = body.sort
    ex("UPDATE albums SET name=?, rules_json=? WHERE id=?", (body.name.strip(), json.dumps(spec), album_id))
    return {"id": album_id, "rules": spec}
