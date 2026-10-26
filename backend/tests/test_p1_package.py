import os
import time
import zipfile

import pytest

from tests.conftest import HEADERS, import_dir, pattern, wait_job

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def packed(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(400, 300).save(src / "one.jpg", "JPEG", quality=90)
    pattern(300, 400, "v").save(src / "two.jpg", "JPEG", quality=90)
    import_dir(client, src)
    ids = [m["id"] for m in client.get("/api/media").json()["items"]]
    out = tmp_path / "out"
    job = client.post("/api/packages", json={"ids": ids, "password": PASSWORD, "dest": str(out), "title": "Trip"}, headers=HEADERS)
    assert job.status_code == 200
    state = wait_job(client, job.json()["job_id"])
    assert state["phase"] == "done", state
    return {"path": state["path"], "ids": ids, "counts": state["counts"]}


def upload(client, path):
    with open(path, "rb") as fh:
        return client.post("/api/packages/inspect", files={"file": ("share.zip", fh, "application/zip")}, headers=HEADERS).json()


def new_library(client, tmp_path, monkeypatch):
    from app.config import library_root

    monkeypatch.setenv("FORMDAM_LIBRARY", library_root())
    other = tmp_path / "second"
    deadline = time.monotonic() + 90
    while True:
        switched = client.post("/api/library/switch", json={"path": str(other), "create": True}, headers=HEADERS)
        if switched.status_code != 409 or time.monotonic() > deadline:
            break
        time.sleep(0.2)
    assert switched.status_code == 200, switched.text
    assert client.get("/api/media").json()["items"] == []


def test_short_password_is_refused_before_a_package_is_built(client, tmp_path):
    body = {"ids": [1], "password": "short", "dest": str(tmp_path / "o")}
    assert client.post("/api/packages", json=body, headers=HEADERS).status_code == 422


def test_package_is_an_encrypted_archive(packed):
    assert packed["counts"]["items"] == 2
    with zipfile.ZipFile(packed["path"]) as zf:
        names = zf.namelist()
        assert "formdam-share.json" in names
        assert all(info.flag_bits & 1 for info in zf.infolist() if info.filename != "formdam-share.json")
        raw = open(packed["path"], "rb").read()
    assert b"Trip" not in raw and b"one.jpg" not in raw


def test_package_exports_then_imports_into_another_library(client, packed, tmp_path, monkeypatch):
    new_library(client, tmp_path, monkeypatch)
    info = upload(client, packed["path"])
    assert info["package"] is True and info["files"] == 2
    opened = client.post("/api/packages/open", json={"token": info["token"], "password": PASSWORD}, headers=HEADERS)
    assert opened.status_code == 200
    assert opened.json()["count"] == 2 and opened.json()["title"] == "Trip"
    state = wait_job(client, opened.json()["job_id"])
    assert state["phase"] == "done" and state["counts"]["imported"] == 2 and state["counts"]["failed"] == 0
    names = sorted(m["name"] for m in client.get("/api/media").json()["items"])
    assert names == ["one.jpg", "two.jpg"]


def test_wrong_password_is_refused_and_imports_nothing(client, packed, tmp_path, monkeypatch):
    new_library(client, tmp_path, monkeypatch)
    info = upload(client, packed["path"])
    for attempt in ("wrong-password-value", PASSWORD.upper(), PASSWORD + " "):
        check = client.post("/api/packages/check", json={"token": info["token"], "password": attempt}, headers=HEADERS)
        assert check.status_code == 403
        opened = client.post("/api/packages/open", json={"token": info["token"], "password": attempt}, headers=HEADERS)
        assert opened.status_code == 403
    assert client.get("/api/media").json()["items"] == []
    assert client.post("/api/packages/check", json={"token": info["token"], "password": PASSWORD}, headers=HEADERS).status_code == 200


def test_a_plain_zip_is_not_a_package(client, tmp_path):
    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("a.txt", "hello")
    assert upload(client, plain) == {"package": False}


def test_unknown_or_malformed_token_is_refused(client):
    for token in ("0" * 32, "../../etc/passwd", "short"):
        assert client.post("/api/packages/open", json={"token": token, "password": PASSWORD}, headers=HEADERS).status_code == 404


def test_private_and_hidden_items_are_never_packaged(client, packed, tmp_path):
    token = client.post("/api/vault/setup", json={"passkey": "packagekey"}, headers=HEADERS).json()["token"]
    first = packed["ids"][0]
    assert client.post(f"/api/media/{first}/hide", headers={**HEADERS, "x-dam-vault": token}).status_code == 200
    job = client.post("/api/packages", json={"ids": packed["ids"], "password": PASSWORD, "dest": str(tmp_path / "o2")}, headers=HEADERS)
    state = wait_job(client, job.json()["job_id"])
    assert state["phase"] == "done" and state["counts"]["items"] == 1 and state["counts"]["skipped"] == 1
