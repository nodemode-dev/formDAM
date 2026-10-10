import json
import threading
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import Response

from .db import reset_thread_conn
from .services import familynet

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_server = None
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()


def _deny(status: int = 404) -> Response:
    return Response(status_code=status)


@app.middleware("http")
async def guard(request: Request, call_next):
    try:
        client = request.client.host if request.client else ""
        if not familynet.private_ip(client) or not familynet.settings()["enabled"]:
            return _deny(403)
        if request.method != "GET" or not request.url.path.startswith("/f/"):
            return _deny()
        if familynet.verify("GET", request.url.path, {k.lower(): v for k, v in request.headers.items()}) is None:
            return _deny(401)
        response = await call_next(request)
    finally:
        reset_thread_conn()
    response.headers["Cache-Control"] = "no-store"
    return response


def _sealed(payload: bytes, path: str) -> Response:
    return Response(familynet.seal(payload, path), media_type="application/octet-stream")


@app.get("/f/hello")
def hello():
    from .services.syncsvc import device_id, device_name

    return _sealed(json.dumps({"dev": device_id(), "name": device_name()}).encode(), "/f/hello")


@app.get("/f/journal")
def journal():
    return _sealed(json.dumps(familynet.journal_listing()).encode(), "/f/journal")


@app.get("/f/journal/{name}")
def journal_file(name: str):
    path = familynet.serve_path("journal", name)
    if path is None:
        return _deny()
    with open(path, "rb") as handle:
        return _sealed(handle.read(), f"/f/journal/{name}")


@app.get("/f/object/{name}")
def object_file(name: str):
    path = familynet.serve_path("object", name)
    if path is None:
        return _deny()
    with open(path, "rb") as handle:
        return _sealed(handle.read(), f"/f/object/{name}")


@app.get("/f/edit/{name}")
def edit_file(name: str):
    path = familynet.serve_path("edit", name)
    if path is None:
        return _deny()
    with open(path, "rb") as handle:
        return _sealed(handle.read(), f"/f/edit/{name}")


def running() -> bool:
    return _thread is not None and _thread.is_alive()


def start() -> bool:
    global _server, _thread
    import uvicorn

    with _lock:
        if running():
            return True
        config = uvicorn.Config(app, host="0.0.0.0", port=familynet.settings()["port"], log_level="warning", access_log=False)
        _server = uvicorn.Server(config)
        _server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        _thread = threading.Thread(target=_server.run, name="DAM-family", daemon=True)
        _thread.start()
    for _ in range(60):
        if _server.started:
            return True
        if not _thread.is_alive():
            return False
        threading.Event().wait(0.05)
    return bool(_server.started)


def stop() -> None:
    global _server, _thread
    with _lock:
        if _server is not None:
            _server.should_exit = True
        if _thread is not None:
            _thread.join(timeout=5)
        _server, _thread = None, None
    familynet.stop_discovery()


def sync_state() -> bool:
    if familynet.settings()["enabled"]:
        ok = start()
        if ok:
            familynet.start_discovery()
        return ok
    stop()
    return False
