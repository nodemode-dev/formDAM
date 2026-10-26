import os

from tests.conftest import HEADERS, import_dir, pattern


def test_trash_lock_restore_and_delete(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "one.jpg", "JPEG")
    pattern(240, 320, "v").save(src / "two.jpg", "JPEG")
    import_dir(client, src)
    a, b = [m["id"] for m in client.get("/api/media").json()["items"]]

    assert client.post(f"/api/media/{a}/trash", headers=HEADERS).status_code == 200
    assert a not in [m["id"] for m in client.get("/api/media").json()["items"]]

    assert client.get("/api/trash").status_code == 401
    token = client.post("/api/vault/setup", json={"passkey": "trashkey"}, headers=HEADERS).json()["token"]
    auth = {**HEADERS, "x-dam-vault": token}
    trash = client.get("/api/trash", headers=auth).json()
    assert [m["id"] for m in trash["items"]] == [a]
    assert trash["items"][0]["days_left"] <= trash["retention_days"]

    assert client.post(f"/api/trash/{a}/restore", headers=auth).status_code == 200
    assert a in [m["id"] for m in client.get("/api/media").json()["items"]]

    client.post(f"/api/media/{b}/trash", headers=HEADERS)
    rel = client.get(f"/api/media/{b}", headers=auth).json()["rel_path"]
    from app.services.libraryfs import abs_path
    on_disk = abs_path(rel)
    assert client.delete(f"/api/trash/{b}", headers=auth).status_code == 200
    assert not os.path.exists(on_disk)
    assert client.get(f"/api/media/{b}", headers=auth).status_code == 404
