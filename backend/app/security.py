import hashlib
import hmac
import os
import re
import time

from fastapi import Request
from fastapi.responses import JSONResponse

LOCAL_HEADER = "x-dam-local"
VAULT_HEADER = "x-dam-vault"
HOST_RE = re.compile(r"^(localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\])(:\d+)?$", re.IGNORECASE)
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


SHELL_HEADER = "x-dam-shell"
AUTOMATION_HEADER = "x-dam-automation"
OPEN_PATHS = {"/api/health"}
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


def automation_allowed(request: Request) -> bool:
    if os.environ.get("DAM_AUTOMATION") == "1":
        return True
    shell = os.environ.get("DAM_SHELL_KEY", "")
    if shell and hmac.compare_digest(request.headers.get(SHELL_HEADER, ""), shell):
        return True
    if request.headers.get("sec-fetch-site") == "same-origin":
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
