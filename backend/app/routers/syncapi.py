from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import setting_get, setting_set
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
    if channel == "shared":
        raise HTTPException(400, detail="The Shared Library works only on your local network with a share key; set it up under Shared Library")
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


class FamilyIn(BaseModel):
    enabled: Optional[bool] = None
    port: Optional[int] = Field(None, ge=1024, le=65535)


class FamilyKeyIn(BaseModel):
    key: Optional[str] = Field(None, max_length=80)


class PeerIn(BaseModel):
    address: str = Field(min_length=3, max_length=200)


def _family():
    from .. import familyserver
    from ..services import familynet

    s = familynet.settings()
    return {**s, "family_id": familynet.family_id(), "running": familyserver.running(), "peers": familynet.peers(),
            "status": syncsvc.config("shared")}


@router.get("/family")
def family_state():
    return _family()


@router.get("/family/key")
def family_key():
    from ..services import familynet

    key = setting_get("family_key") or ""
    return {"key": familynet.pretty_key(key) if key else ""}


@router.post("/family/key")
def set_family_key(body: FamilyKeyIn):
    from ..services import familynet

    if familynet.settings()["enabled"]:
        raise HTTPException(409, detail="Turn the Shared Library off before changing its key")
    if body.key:
        key = familynet.normalize_key(body.key)
        if key is None:
            raise HTTPException(400, detail="That is not a DAM share key (32 letters and digits, dashes optional)")
    else:
        key = familynet.new_key()
    setting_set("family_key", key)
    return {"key": familynet.pretty_key(key), "family_id": familynet.family_id()}


@router.put("/family")
def put_family(body: FamilyIn):
    from .. import familyserver
    from ..services import familynet

    if body.port is not None:
        if familyserver.running():
            familyserver.stop()
        setting_set("family_port", str(body.port))
    if body.enabled is not None:
        if body.enabled and not familynet.settings()["has_key"]:
            raise HTTPException(400, detail="Create a share key or paste one from another family member first")
        setting_set("family_enabled", "1" if body.enabled else "0")
    ok = familyserver.sync_state()
    if familynet.settings()["enabled"] and not ok:
        setting_set("family_enabled", "0")
        raise HTTPException(409, detail=f"Port {familynet.settings()['port']} is in use. Pick another port.")
    if familynet.settings()["enabled"]:
        syncsvc.sync_now()
    return _family()


@router.post("/family/peers")
def add_peer(body: PeerIn):
    from ..services import familynet

    if not familynet.settings()["enabled"]:
        raise HTTPException(400, detail="Turn the Shared Library on first")
    try:
        peer = familynet.add_manual(body.address)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    except Exception:
        raise HTTPException(502, detail="That device did not answer, or holds a different share key")
    syncsvc.sync_now()
    return peer


@router.post("/media/shared-library")
def move_library(body: SharedIn):
    changed = syncsvc.set_shared(body.ids, body.shared)
    return {"changed": changed, "skipped": len(body.ids) - changed}
