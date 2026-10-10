import os
import time
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import jobs, macshare, shareserver
from ..db import ex, q1
from ..services import filesvc, sharesvc

router = APIRouter()


class SettingsIn(BaseModel):
    enabled: Optional[bool] = None
    port: Optional[int] = Field(None, ge=1024, le=65535)
    name: Optional[str] = Field(None, max_length=sharesvc.MAX_NAME)


class LinkIn(BaseModel):
    ids: List[int] = Field(default_factory=list, max_length=20000)
    title: str = Field("", max_length=120)
    expires_days: Optional[float] = Field(None, gt=0, le=3650)
    password: Optional[str] = Field(None, max_length=200)
    allow_download: bool = True
    allow_comments: bool = True
    allow_contrib: bool = False
    include_location: bool = False


class OwnerPostIn(BaseModel):
    text: str = Field(min_length=1, max_length=sharesvc.MAX_TEXT)
    media_id: Optional[int] = None


class SendIn(BaseModel):
    service: str = Field(pattern="^(airdrop|mail|messages)$")
    ids: List[int] = Field(default_factory=list, max_length=200)
    share_id: Optional[int] = None


class GalleryIn(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=20000)
    title: str = Field("Web Gallery", max_length=120)
    dest: str = Field(min_length=1)
    include_location: bool = False


def _share_row(share_id: int):
    row = q1("SELECT * FROM shares WHERE id=? AND revoked=0", (share_id,))
    if row is None:
        raise HTTPException(404, detail="No such share")
    return row


@router.get("/sharing/settings")
def get_settings():
    return {**sharesvc.settings(), "running": shareserver.running(), "urls": sharesvc.base_urls(), "native": macshare.available()}


@router.put("/sharing/settings")
def put_settings(body: SettingsIn):
    before = sharesvc.settings()
    sharesvc.save_settings(body.enabled, body.port, body.name)
    if body.port is not None and body.port != before["port"] and shareserver.running():
        shareserver.stop()
    ok = shareserver.sync_state()
    if sharesvc.settings()["enabled"] and not ok:
        raise HTTPException(409, detail=f"Port {sharesvc.settings()['port']} is in use. Pick another port.")
    return get_settings()


@router.get("/sharing")
def list_shares():
    return {"shares": sharesvc.listing(), "running": shareserver.running()}


@router.post("/sharing/links")
def create_link(body: LinkIn):
    if not body.ids:
        raise HTTPException(400, detail="Choose something to share")
    share = sharesvc.create("link", body.title or "Shared Photos", ids=body.ids, expires_days=body.expires_days,
                            password=body.password or None, allow_download=body.allow_download,
                            allow_comments=body.allow_comments, include_location=body.include_location)
    if share["count"] == 0:
        ex("UPDATE shares SET revoked=1 WHERE id=?", (share["id"],))
        raise HTTPException(409, detail="Private, hidden and deleted items are never shared")
    return {**share, "skipped": len(body.ids) - share["count"]}


@router.post("/sharing/albums/{album_id}")
def share_album(album_id: int, body: LinkIn):
    album = q1("SELECT * FROM albums WHERE id=?", (album_id,))
    if album is None:
        raise HTTPException(404, detail="No such album")
    if album["is_private"]:
        raise HTTPException(409, detail="Private albums are never shared")
    existing = q1("SELECT * FROM shares WHERE kind='album' AND album_id=? AND revoked=0", (album_id,))
    if existing:
        ex("UPDATE shares SET allow_download=?, allow_comments=?, allow_contrib=?, include_location=? WHERE id=?",
           (int(body.allow_download), int(body.allow_comments), int(body.allow_contrib), int(body.include_location), existing["id"]))
        return sharesvc.describe(q1("SELECT * FROM shares WHERE id=?", (existing["id"],)))
    return sharesvc.create("album", body.title or album["name"], album_id=album_id, expires_days=body.expires_days,
                           password=body.password or None, allow_download=body.allow_download, allow_comments=body.allow_comments,
                           allow_contrib=body.allow_contrib, include_location=body.include_location)


@router.delete("/sharing/{share_id}")
def revoke(share_id: int):
    _share_row(share_id)
    ex("UPDATE shares SET revoked=1 WHERE id=?", (share_id,))
    return {"ok": True}


@router.get("/sharing/{share_id}/activity")
def share_activity(share_id: int):
    row = _share_row(share_id)
    ex("UPDATE shares SET seen_ts=? WHERE id=?", (time.time(), share_id))
    return {"share": sharesvc.describe(row), "activity": sharesvc.activity(share_id)}


@router.post("/sharing/{share_id}/comment")
def owner_comment(share_id: int, body: OwnerPostIn):
    row = _share_row(share_id)
    if body.media_id is not None and not sharesvc.allowed(row, body.media_id):
        raise HTTPException(404, detail="Not in this share")
    return sharesvc.post(row, "comment", sharesvc.settings()["name"], body.text, body.media_id, owner=True)


@router.get("/sharing/{share_id}/qr.png")
def share_qr(share_id: int):
    row = _share_row(share_id)
    data = sharesvc.qr_png(sharesvc.url_for(row["token"]))
    if not data:
        raise HTTPException(500, detail="Could not draw the code")
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/sharing/send")
def send(body: SendIn):
    items: List[str] = []
    subject = "Photos"
    if body.share_id is not None:
        row = _share_row(body.share_id)
        items = [sharesvc.url_for(row["token"])]
        subject = row["title"]
    else:
        fake = {"include_location": 0, "allow_download": 1}
        for media_id in sharesvc._shareable_ids(body.ids):
            path = sharesvc.download_path(fake, media_id)
            if path:
                items.append(path)
    if not items:
        raise HTTPException(409, detail="Private, hidden and deleted items are never shared")
    if macshare.launch(body.service, items, subject):
        return {"ok": True, "native": True}
    if body.service == "mail" and body.share_id is not None:
        return {"ok": filesvc.open_url(f"mailto:?subject={quote(subject)}&body={quote(items[0])}"), "native": False}
    raise HTTPException(501, detail="AirDrop and Messages need the Mac app. Copy the link or export a web gallery instead.")


@router.post("/sharing/gallery")
def gallery(body: GalleryIn):
    dest = os.path.abspath(os.path.expanduser(body.dest))
    if not os.path.isdir(dest):
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError:
            raise HTTPException(400, detail="That folder cannot be created")
    return {"job_id": jobs.start("gallery", lambda state: sharesvc.web_gallery(body.ids, body.title, dest, body.include_location, state))}
