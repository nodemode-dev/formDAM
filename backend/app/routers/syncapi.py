from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import setting_set
from ..services import syncsvc

router = APIRouter()


class ChannelIn(BaseModel):
    folder: Optional[str] = Field(None, max_length=1024)
    enabled: bool = True


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class SharedIn(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=20000)
    shared: bool = True


def _payload():
    return {"device": {"id": syncsvc.device_id(), "name": syncsvc.device_name()},
            "channels": {c: {**syncsvc.config(c), "devices": syncsvc.devices(c)} for c in syncsvc.CHANNELS}}


@router.get("/sync")
def sync_state():
    return _payload()


@router.put("/sync/device")
def set_device(body: DeviceIn):
    setting_set("sync_device_name", body.name.strip())
    syncsvc.sync_now()
    return _payload()


@router.put("/sync/{channel}")
def set_channel(channel: str, body: ChannelIn):
    if channel not in syncsvc.CHANNELS:
        raise HTTPException(404, detail="No such sync channel")
    if body.enabled and not (body.folder or syncsvc.config(channel)["folder"]):
        raise HTTPException(400, detail="Choose a folder first")
    try:
        syncsvc.configure(channel, body.folder, body.enabled)
    except OSError as exc:
        raise HTTPException(400, detail=f"That folder cannot be used: {exc.strerror or exc}")
    return _payload()


@router.post("/sync/now")
def sync_now():
    syncsvc.sync_now()
    return {"ok": True}


@router.post("/media/shared-library")
def move_library(body: SharedIn):
    changed = syncsvc.set_shared(body.ids, body.shared)
    return {"changed": changed, "skipped": len(body.ids) - changed}
