import hashlib
import os
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..db import setting_get, setting_set
from ..security import SESSION_COOKIE, WINDOW_SESSION, forget_automation, shell_allowed, window_allowed

router = APIRouter()


class AutomationIn(BaseModel):
    enabled: bool


def _from_window(request: Request) -> bool:
    return window_allowed(request) or os.environ.get("FORMDAM_AUTOMATION") == "1"


@router.get("/session")
def session_state(request: Request):
    return {"window": window_allowed(request)}


@router.post("/session")
def open_session(request: Request, response: Response):
    if not shell_allowed(request):
        raise HTTPException(403, detail="This window was not opened by formDAM. Open formDAM from its app or its launcher.")
    response.set_cookie(SESSION_COOKIE, WINDOW_SESSION, httponly=True, samesite="strict", path="/")
    return {"window": True}


def _state():
    return {"enabled": setting_get("automation_enabled") == "1", "has_token": bool(setting_get("automation_token")),
            "created_ts": float(setting_get("automation_created") or 0) or None,
            "forced": os.environ.get("FORMDAM_AUTOMATION") == "1"}


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
            raise HTTPException(403, detail="Automation can only be turned on from the formDAM window")
        setting_set("automation_enabled", "1")
        token = _issue()
        return {**_state(), "token": token}
    setting_set("automation_enabled", "0")
    setting_set("automation_token", "")
    forget_automation()
    return _state()


@router.post("/system/automation/rotate")
def rotate_automation(request: Request):
    if not _from_window(request):
        raise HTTPException(403, detail="A new token can only be made from the formDAM window")
    if setting_get("automation_enabled") != "1":
        raise HTTPException(409, detail="Turn Automation Access on first")
    token = _issue()
    return {**_state(), "token": token}
