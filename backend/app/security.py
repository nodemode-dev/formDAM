import hashlib
import hmac
import os
import re
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse

LOCAL_HEADER = "x-dam-local"
VAULT_HEADER = "x-dam-vault"
HOST_RE = re.compile(r"^(localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\])(:\d+)?$", re.IGNORECASE)
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


SHELL_HEADER = "x-dam-shell"
AUTOMATION_HEADER = "x-dam-automation"
SESSION_COOKIE = "dam_session"
OPEN_PATHS = {"/api/health", "/api/session"}
_LEGACY_KEY = os.environ.pop("DAM_SHELL_KEY", "")
_ENV_KEY = os.environ.pop("FORMDAM_SHELL_KEY", "") or _LEGACY_KEY
LAUNCH_KEY = _ENV_KEY or secrets.token_hex(32)
LAUNCH_GENERATED = not _ENV_KEY
WINDOW_SESSION = hmac.new(LAUNCH_KEY.encode(), b"dam-window-session", hashlib.sha256).hexdigest()
AUTOMATION_OFF = ("Automation access is off. Scripts, agents and MCP tools can use DAM only after you turn on "
                  "Automation Access in Settings > Privacy and give them the token it shows.")
_cache: dict = {"ts": 0.0, "enabled": False, "hash": ""}


def _automation_state() -> tuple:
    now = time.monotonic()
    if now - _cache["ts"] > 2.0:
        from .db import setting_get

        try:
            _cache.update(ts=now, enabled=setting_get("automation_enabled") == "1", hash=setting_get("automation_token") or "")
        except Exception:
            _cache.update(ts=now, enabled=False, hash="")
    return _cache["enabled"], _cache["hash"]


def forget_automation() -> None:
    _cache["ts"] = 0.0


def shell_allowed(request: Request) -> bool:
    return hmac.compare_digest(request.headers.get(SHELL_HEADER, ""), LAUNCH_KEY)


def window_allowed(request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get(SESSION_COOKIE, ""), WINDOW_SESSION)


def automation_allowed(request: Request) -> bool:
    if os.environ.get("DAM_AUTOMATION") == "1":
        return True
    if shell_allowed(request) or window_allowed(request):
        return True
    token = request.headers.get(AUTOMATION_HEADER, "")
    if token:
        enabled, stored = _automation_state()
        digest = hashlib.sha256(token.encode()).hexdigest()
        return enabled and bool(stored) and hmac.compare_digest(digest, stored)
    return False


def is_loopback_ip(host: str) -> bool:
    return host == "::1" or host == "localhost" or host.startswith("127.")


def host_allowed(host_header: str) -> bool:
    return bool(HOST_RE.match(host_header.strip()))


async def local_only_guard(request: Request, call_next):
    client = request.client
    if client is not None and not is_loopback_ip(client.host):
        return JSONResponse(status_code=403, content={"detail": "DAM only accepts local loopback connections"})
    if not host_allowed(request.headers.get("host", "")):
        return JSONResponse(status_code=403, content={"detail": "Rejected non-local Host header"})
    if request.method in MUTATING and request.url.path.startswith("/api") and request.headers.get(LOCAL_HEADER) != "1":
        return JSONResponse(status_code=403, content={"detail": "Missing local client header"})
    if request.url.path.startswith("/api/") and request.url.path not in OPEN_PATHS and not automation_allowed(request):
        return JSONResponse(status_code=403, content={"detail": AUTOMATION_OFF})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response
