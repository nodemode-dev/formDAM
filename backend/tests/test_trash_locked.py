import os
import time

from starlette.testclient import TestClient

from tests.conftest import HEADERS, import_dir, pattern

LOCKED = "a1.jpg"


def seed(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    for i in range(3):
        pattern(64 + i, 48).save(src / f"a{i}.jpg", "JPEG")
    import_dir(client, src)
    from app.db import ex

    ex("UPDATE media SET trashed_ts=?, trash_reason='duplicate:1'", (time.time() - 90 * 86400,))


def lock(monkeypatch):
    real = os.unlink

    def unlink(path, *args, **kwargs):
        if os.path.basename(str(path)) == LOCKED:
            raise PermissionError(13, "in use", str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink)


def names():
    from app.db import q

    return sorted(r["name"] for r in q("SELECT name FROM media"))


def test_a_locked_file_does_not_stop_the_expired_purge(client, tmp_path, monkeypatch):
    from app.routers import trash

    seed(client, tmp_path)
    lock(monkeypatch)
    assert trash.purge_expired() == 2
    assert names() == [LOCKED]


def test_a_locked_file_does_not_stop_the_engine_from_starting(client, tmp_path, monkeypatch):
    seed(client, tmp_path)
    lock(monkeypatch)
    with TestClient(client.app, base_url="http://127.0.0.1", client=("127.0.0.1", 51234)):
        pass
    assert names() == [LOCKED]


def test_a_locked_file_stays_in_the_trash_and_goes_once_free(client, tmp_path, monkeypatch):
    from app.routers import trash

    seed(client, tmp_path)
    with monkeypatch.context() as inner:
        lock(inner)
        assert trash.purge_expired() == 2
    assert names() == [LOCKED]
    assert trash.purge_expired() == 1
    assert names() == []


def test_deleting_a_locked_file_forever_says_so_and_keeps_it(client, tmp_path, monkeypatch):
    token = client.post("/api/vault/setup", json={"passkey": "trashkey"}, headers=HEADERS).json()["token"]
    auth = {**HEADERS, "x-dam-vault": token}
    seed(client, tmp_path)
    from app.db import q1

    locked = q1("SELECT id FROM media WHERE name=?", (LOCKED,))["id"]
    lock(monkeypatch)
    refused = client.delete(f"/api/trash/{locked}", headers=auth)
    assert refused.status_code == 409
    assert names() == ["a0.jpg", "a1.jpg", "a2.jpg"]
    emptied = client.post("/api/trash/empty", headers=auth)
    assert emptied.json() == {"deleted": 2}
    assert names() == [LOCKED]
