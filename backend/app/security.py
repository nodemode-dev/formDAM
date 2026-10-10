import re

from fastapi import Request
from fastapi.responses import JSONResponse

LOCAL_HEADER = "x-dam-local"
VAULT_HEADER = "x-dam-vault"
HOST_RE = re.compile(r"^(localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\])(:\d+)?$", re.IGNORECASE)
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


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
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response
