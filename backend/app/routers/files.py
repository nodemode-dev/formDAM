import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import jobs
from ..db import q1
from ..services import filesvc, libraryfs, renamesvc
from .guard import ensure_visible

router = APIRouter()


class RenameIn(BaseModel):
    ids: List[int]
    template: str = Field(min_length=1, max_length=300)
    start: int = 1
    custom: str = ""


class CopyIn(BaseModel):
    ids: List[int]
    dest: str = Field(min_length=1)


class OpenIn(BaseModel):
    app: Optional[str] = None


def _check(ids: List[int], request: Request) -> None:
    for media_id in ids:
        ensure_visible(q1("SELECT * FROM media WHERE id=?", (media_id,)), request)


@router.get("/rename/tokens")
def rename_tokens():
    return {"tokens": renamesvc.TOKENS}


@router.post("/media/rename/preview")
def rename_preview(body: RenameIn, request: Request):
    _check(body.ids, request)
    return {"plan": filesvc.rename_plan(body.ids, body.template, body.start, body.custom)}


@router.post("/media/rename")
def rename(body: RenameIn, request: Request):
    _check(body.ids, request)
    return {"plan": filesvc.rename(body.ids, body.template, body.start, body.custom)}


@router.post("/media/copy-to", status_code=202)
def copy_to(body: CopyIn, request: Request):
    _check(body.ids, request)
    dest = os.path.abspath(os.path.expanduser(body.dest))
    return {"job_id": jobs.start("copy", lambda state: filesvc.copy_originals(body.ids, dest, state))}


def _path(media_id: int, request: Request) -> str:
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    from .. import vaultcrypt
    if vaultcrypt.protected(row) or vaultcrypt.is_vaulted(media_id):
        raise HTTPException(409, detail="Protected items stay inside the vault")
    path = libraryfs.abs_path(row["rel_path"])
    if not os.path.isfile(path):
        raise HTTPException(404, detail="Original file missing on disk")
    return path


@router.post("/media/{media_id}/reveal")
def reveal(media_id: int, request: Request):
    return {"ok": filesvc.reveal(_path(media_id, request))}


@router.post("/media/{media_id}/open")
def open_with(media_id: int, body: OpenIn, request: Request):
    return {"ok": filesvc.open_with(_path(media_id, request), body.app)}


@router.get("/system/editors")
def editors():
    return {"apps": filesvc.editor_apps()}
