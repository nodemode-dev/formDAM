import os
import sys
import time

import pytest
from PIL import Image
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HEADERS = {"x-dam-local": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DAM_LIBRARY", str(tmp_path / "library"))
    from app.db import reset_thread_conn
    reset_thread_conn()
    from app.main import app
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 51234)) as tc:
        yield tc
    reset_thread_conn()


def pattern(width, height, tilt="h"):
    img = Image.new("L", (width, height))
    px = img.load()
    for y in range(height):
        for x in range(width):
            px[x, y] = int(255 * (x / width if tilt == "h" else (height - y) / height))
    for y in range(height // 6, height // 3):
        for x in range(int(width * 0.62), int(width * 0.95)):
            px[x, y] = 10
    return img.convert("RGB")


def wait_job(tc, job_id, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = tc.get(f"/api/jobs/{job_id}").json()
        if state["phase"] in {"done", "error"}:
            return state
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} timed out: {state}")


def import_dir(tc, path, move=False):
    created = tc.post("/api/import", json={"path": str(path), "move": move}, headers=HEADERS)
    assert created.status_code == 202
    state = wait_job(tc, created.json()["job_id"])
    assert state["phase"] == "done", state
    return state["counts"]
