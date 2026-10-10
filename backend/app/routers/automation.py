import hashlib
import os
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..db import setting_get, setting_set
from ..security import forget_automation

router = APIRouter()


class AutomationIn(BaseModel):
    enabled: bool


def _from_window(request: Request) -> bool:
    return request.headers.get("sec-fetch-site") == "same-origin" or os.environ.get("DAM_AUTOMATION") == "1"


def _state():
    return {"enabled": setting_get("automation_enabled") == "1", "has_token": bool(setting_get("automation_token")),
            "created_ts": float(setting_get("automation_created") or 0) or None,
            "forced": os.environ.get("DAM_AUTOMATION") == "1"}


def _issue() -> str:
    token = "dam_" + secrets.token_urlsafe(32)
    setting_set("automation_token", hashlib.sha256(token.encode()).hexdigest())
    setting_set("automation_created", str(time.time()))
    forget_automation()
    return token


@router.get("/system/automation")
def automation_state():
    return _state()


@router.put("/system/automation")
def set_automation(body: AutomationIn, request: Request):
    if body.enabled:
        if not _from_window(request):
            raise HTTPException(403, detail="Automation can only be turned on from the DAM window")
        setting_set("automation_enabled", "1")
        return {**_state(), "token": _issue()}
    setting_set("automation_enabled", "0")
    setting_set("automation_token", "")
    forget_automation()
    return _state()


@router.post("/system/automation/rotate")
def rotate_automation(request: Request):
    if not _from_window(request):
        raise HTTPException(403, detail="A new token can only be made from the DAM window")
    if setting_get("automation_enabled") != "1":
        raise HTTPException(409, detail="Turn Automation Access on first")
    return {**_state(), "token": _issue()}
