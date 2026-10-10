import os

import pytest

from app.services import facesvc
from tests.conftest import HEADERS, import_dir, pattern, wait_job


def test_status_shape(client):
    body = client.get("/api/people/status").json()
    assert set(["cv2", "models", "ready", "pending_media"]).issubset(body)


def test_scan_marks_faceless_media(client, tmp_path):
    if not facesvc.status()["ready"]:
        pytest.skip("face engine not ready in this environment")
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "one.jpg", "JPEG")
    import_dir(client, src)
    job = client.post("/api/people/scan", headers=HEADERS).json()["job_id"]
    state = wait_job(client, job)
    assert state["counts"]["scanned"] == 1
    assert client.get("/api/people/status").json()["pending_media"] == 0
    assert client.get("/api/people").json()["people"] == []
