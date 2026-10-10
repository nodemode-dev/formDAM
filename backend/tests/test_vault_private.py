import os

from tests.conftest import HEADERS, import_dir, pattern


def test_private_album_flow(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "one.jpg", "JPEG")
    pattern(240, 320, "v").save(src / "two.jpg", "JPEG")
    import_dir(client, src)
    items = client.get("/api/media").json()["items"]
    target = items[0]["id"]

    assert client.get("/api/vault/status").json()["configured"] is False
    made = client.post("/api/albums", json={"name": "Secrets", "is_private": True, "passkey": "hunter22"}, headers=HEADERS)
    assert made.status_code == 201
    album_id = made.json()["id"]

    assert client.get(f"/api/albums/{album_id}").status_code == 401
    assert client.post(f"/api/albums/{album_id}/unlock", json={"passkey": "nope-nope"}, headers=HEADERS).status_code == 401
    token = client.post(f"/api/albums/{album_id}/unlock", json={"passkey": "hunter22"}, headers=HEADERS).json()["token"]
    auth = {**HEADERS, "x-dam-vault": token}

    assert client.post(f"/api/albums/{album_id}/items", json={"media_ids": [target]}, headers=auth).json()["added"] == 1
    public = [m["id"] for m in client.get("/api/media").json()["items"]]
    assert target not in public
    assert client.get(f"/api/media/{target}").status_code == 401
    assert client.get(f"/api/media/{target}", headers=auth).status_code == 200
    detail = client.get(f"/api/albums/{album_id}", headers=auth).json()
    assert [m["id"] for m in detail["items"]] == [target]

    assert client.request("DELETE", f"/api/albums/{album_id}/items", json={"media_ids": [target]}, headers=auth).status_code == 200
    assert target in [m["id"] for m in client.get("/api/media").json()["items"]]


def test_vault_token_opens_private_albums(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "one.jpg", "JPEG")
    import_dir(client, src)
    vault_token = client.post("/api/vault/setup", json={"passkey": "rootkey9"}, headers=HEADERS).json()["token"]
    made = client.post("/api/albums", json={"name": "Locked", "is_private": True}, headers=HEADERS).json()
    auth = {**HEADERS, "x-dam-vault": vault_token}
    assert client.get(f"/api/albums/{made['id']}", headers=auth).status_code == 200
