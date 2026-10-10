import os
import re
import secrets
import time
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import jobs, macshare
from ..db import q, q1
from ..services import filesvc, packagesvc

router = APIRouter()
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
INCOMING_TTL_S = 24 * 3600
MAX_PACKAGE = 64 * 1024 * 1024 * 1024


class BuildIn(BaseModel):
    ids: List[int] = Field(default_factory=list, max_length=50000)
    album_id: Optional[int] = None
    title: str = Field("", max_length=120)
    password: str = Field(min_length=packagesvc.MIN_PASSWORD, max_length=200)
    dest: str = Field(min_length=1, max_length=1024)
    include_location: bool = False
    add_as: str = Field("album", pattern="^(album|stack)$")
    sender: str = Field("", max_length=60)


class OpenIn(BaseModel):
    token: str
    password: str = Field(min_length=1, max_length=200)
    add_as: Optional[str] = Field(None, pattern="^(album|stack)$")


class SendIn(BaseModel):
    package: int
    service: str = Field(pattern="^(airdrop|mail|messages|reveal)$")


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=packagesvc.MAX_NOTE)
    author: str = Field("", max_length=60)


def _incoming(token: str) -> str:
    if not TOKEN_RE.match(token):
        raise HTTPException(404, detail="That package is no longer waiting")
    path = os.path.join(packagesvc.incoming_dir(), token + ".zip")
    if not os.path.isfile(path):
        raise HTTPException(404, detail="That package is no longer waiting")
    return path


def _sweep() -> None:
    folder = packagesvc.incoming_dir()
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if time.time() - os.path.getmtime(path) > INCOMING_TTL_S:
                os.unlink(path)
        except OSError:
            pass


@router.get("/packages")
def list_packages():
    rows = q("SELECT * FROM share_packages ORDER BY created_ts DESC LIMIT 200")
    out = []
    for r in rows:
        d = dict(r)
        d["exists"] = bool(r["path"]) and os.path.isfile(r["path"])
        out.append(d)
    return {"packages": out, "native": macshare.available()}


@router.post("/packages/password")
def suggest_password():
    return {"password": packagesvc.new_password()}


@router.post("/packages")
def build_package(body: BuildIn):
    if body.album_id is None and not body.ids:
        raise HTTPException(400, detail="Choose something to share")
    dest = os.path.abspath(os.path.expanduser(body.dest))

    def run(state):
        try:
            packagesvc.build(body.ids, body.password, body.title.strip(), dest, body.include_location, body.add_as,
                             body.album_id, body.sender.strip(), state)
        except packagesvc.PackageError as exc:
            state["message"] = str(exc)
            raise

    return {"job_id": jobs.start("package", run)}


@router.post("/packages/inspect")
def inspect_package(file: UploadFile = File(...)):
    _sweep()
    token = secrets.token_hex(16)
    path = os.path.join(packagesvc.incoming_dir(), token + ".zip")
    size = 0
    with open(path, "wb") as handle:
        while True:
            chunk = file.file.read(4 * 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_PACKAGE:
                handle.close()
                os.unlink(path)
                raise HTTPException(413, detail="That file is too large")
            handle.write(chunk)
    info = packagesvc.inspect(path)
    if not info["package"]:
        os.unlink(path)
        return {"package": False}
    return {**info, "token": token}


@router.post("/packages/check")
def check_package(body: OpenIn):
    path = _incoming(body.token)
    try:
        return packagesvc.check_password(path, body.password)
    except packagesvc.PackageError as exc:
        raise HTTPException(403, detail=str(exc))


@router.post("/packages/open")
def open_package(body: OpenIn):
    path = _incoming(body.token)
    try:
        info = packagesvc.check_password(path, body.password)
    except packagesvc.PackageError as exc:
        raise HTTPException(403, detail=str(exc))
    return {**info, "job_id": jobs.start("package-open", lambda state: packagesvc.open_package(path, body.password, body.add_as, state))}


@router.delete("/packages/incoming/{token}")
def discard_incoming(token: str):
    path = _incoming(token)
    os.unlink(path)
    return {"ok": True}


@router.post("/packages/send")
def send_package(body: SendIn):
    row = q1("SELECT * FROM share_packages WHERE id=? AND direction='out'", (body.package,))
    if row is None or not row["path"] or not os.path.isfile(row["path"]):
        raise HTTPException(404, detail="That package file is gone")
    if body.service == "reveal":
        return {"ok": filesvc.reveal(row["path"])}
    if macshare.launch(body.service, [row["path"]], row["title"]):
        return {"ok": True}
    raise HTTPException(501, detail="Mail, Messages and AirDrop are offered by the Mac app; reveal the file and send it yourself")


class GalleryIn(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=20000)
    title: str = Field("Web Gallery", max_length=120)
    dest: str = Field(min_length=1)
    include_location: bool = False


@router.post("/packages/gallery")
def gallery(body: GalleryIn):
    from ..services import gallerysvc

    dest = os.path.abspath(os.path.expanduser(body.dest))
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError:
        raise HTTPException(400, detail="That folder cannot be created")
    return {"job_id": jobs.start("gallery", lambda state: gallerysvc.web_gallery(body.ids, body.title, dest, body.include_location, state))}


@router.get("/albums/{album_id}/notes")
def album_notes(album_id: int):
    album = q1("SELECT id, is_private, share_uuid FROM albums WHERE id=?", (album_id,))
    if album is None:
        raise HTTPException(404, detail="No such album")
    return {"shared": bool(album["share_uuid"]),
            "notes": [dict(r) for r in q("SELECT * FROM album_notes WHERE album_id=? ORDER BY ts", (album_id,))]}


@router.post("/albums/{album_id}/notes")
def add_album_note(album_id: int, body: NoteIn):
    album = q1("SELECT id, is_private FROM albums WHERE id=?", (album_id,))
    if album is None or album["is_private"]:
        raise HTTPException(404, detail="No such album")
    from ..services import syncsvc

    try:
        return packagesvc.add_note(album_id, body.author.strip() or syncsvc.device_name(), body.text)
    except packagesvc.PackageError as exc:
        raise HTTPException(400, detail=str(exc))
