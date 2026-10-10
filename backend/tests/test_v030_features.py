import os

from tests.conftest import HEADERS, import_dir, pattern, wait_job


def _vault(client):
    token = client.post("/api/vault/setup", json={"passkey": "vault-key-1"}, headers=HEADERS).json()["token"]
    return {**HEADERS, "x-dam-vault": token}


def test_hidden_flow(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "one.jpg", "JPEG")
    pattern(240, 320, "v").save(src / "two.jpg", "JPEG")
    import_dir(client, src)
    a = client.get("/api/media").json()["items"][0]["id"]

    assert client.post(f"/api/media/{a}/hide", headers=HEADERS).status_code == 200
    assert a not in [m["id"] for m in client.get("/api/media").json()["items"]]
    assert client.get("/api/summary").json()["hidden"] == 1

    assert client.get("/api/hidden").status_code == 401
    auth = _vault(client)
    hidden = client.get("/api/hidden", headers=auth).json()["items"]
    assert [m["id"] for m in hidden] == [a]
    assert client.post(f"/api/hidden/{a}/unhide", headers=auth).status_code == 200
    assert a in [m["id"] for m in client.get("/api/media").json()["items"]]


def test_search_by_name(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "beach-sunset.jpg", "JPEG")
    pattern(240, 320, "v").save(src / "mountain.jpg", "JPEG")
    import_dir(client, src)
    found = client.get("/api/media/search", params={"q": "sunset"}).json()["items"]
    assert len(found) == 1 and found[0]["name"] == "beach-sunset.jpg"
    assert client.get("/api/media/search", params={"q": "zzz-nothing"}).json()["items"] == []


def test_screenshot_requires_screen_dims(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(400, 300).save(src / "artboard.png", "PNG")
    pattern(1470, 956).save(src / "capture.png", "PNG")
    pattern(300, 400, "v").save(src / "Screenshot 2026.png", "PNG")
    import_dir(client, src)
    shots = {m["name"] for m in client.get("/api/media", params={"filter": "screenshots"}).json()["items"]}
    assert shots == {"capture.png", "Screenshot 2026.png"}


def test_people_merge_hide_delete_and_unassign(client, tmp_path):
    from app.db import ex
    import numpy as np

    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "one.jpg", "JPEG")
    pattern(240, 320, "v").save(src / "two.jpg", "JPEG")
    import_dir(client, src)
    ids = [m["id"] for m in client.get("/api/media").json()["items"]]

    p1 = ex("INSERT INTO people(name, created_ts, hidden) VALUES('Ada', 1, 0)")
    p2 = ex("INSERT INTO people(name, created_ts, hidden) VALUES(NULL, 1, 0)")
    emb = np.ones(128, dtype=np.float32).tobytes()
    f1 = ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.3,0.3,0.9,?,?)", (ids[0], emb, p1))
    ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.2,0.2,0.8,?,?)", (ids[1], emb, p2))

    people = client.get("/api/people").json()["people"]
    assert len(people) == 2

    assert client.post("/api/people/merge", json={"into_id": p1, "from_ids": [p2]}, headers=HEADERS).json()["moved_faces"] == 1
    people = client.get("/api/people").json()["people"]
    assert len(people) == 1 and people[0]["faces"] == 2

    assert client.patch(f"/api/people/{p1}/hidden", json={"hidden": True}, headers=HEADERS).status_code == 200
    assert client.get("/api/people").json()["people"] == []
    assert len(client.get("/api/people", params={"include_hidden": "true"}).json()["people"]) == 1
    client.patch(f"/api/people/{p1}/hidden", json={"hidden": False}, headers=HEADERS)

    faces = client.get(f"/api/people/{p1}/faces").json()["faces"]
    assert faces[0]["id"] == f1
    assert client.delete(f"/api/faces/{f1}/person", headers=HEADERS).status_code == 200
    assert client.get("/api/people").json()["people"][0]["faces"] == 1

    assert client.delete(f"/api/people/{p1}", headers=HEADERS).status_code == 200
    assert client.get("/api/people").json()["people"] == []


def test_dedup_member_trash_and_auto_exact(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    base = pattern(400, 300)
    base.save(src / "master.png", "PNG")
    base.resize((200, 150)).save(src / "copy1.jpg", "JPEG", quality=82)
    base.resize((220, 165)).save(src / "copy2.jpg", "JPEG", quality=82)
    import_dir(client, src)
    job = client.post("/api/dedup/scan", json={"include_videos": False}, headers=HEADERS).json()["job_id"]
    wait_job(client, job)
    sets = client.get("/api/dedup/sets").json()["sets"]
    assert len(sets) == 1 and sets[0]["reclaimable"] > 0
    set_id = sets[0]["id"]
    victim = sets[0]["members"][0]["id"]
    assert client.post(f"/api/dedup/sets/{set_id}/members/{victim}/trash", headers=HEADERS).json()["trashed"] == 1
    remaining = client.get("/api/dedup/sets").json()["sets"]
    assert remaining and len(remaining[0]["members"]) == 1


def test_fs_and_prefs_and_health_paths(client, tmp_path):
    roots = client.get("/api/fs/roots").json()["roots"]
    assert any(r["kind"] == "home" for r in roots)
    listing = client.get("/api/fs/browse", params={"path": str(tmp_path)}).json()
    assert listing["path"] == str(tmp_path)

    assert client.put("/api/prefs/collections", json={"value": {"order": ["people"], "hidden": ["trips"]}}, headers=HEADERS).status_code == 200
    assert client.get("/api/prefs/collections").json()["value"] == {"order": ["people"], "hidden": ["trips"]}

    health = client.get("/api/health").json()
    assert health["db"].endswith("dam.db")


def test_face_reassign_and_rebuild(client, tmp_path):
    import numpy as np

    from app.db import ex

    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "a.jpg", "JPEG")
    pattern(240, 320, "v").save(src / "b.jpg", "JPEG")
    import_dir(client, src)
    ids = [m["id"] for m in client.get("/api/media").json()["items"]]

    vec_a = np.zeros(128, dtype=np.float32)
    vec_a[0] = 1.0
    vec_b = np.zeros(128, dtype=np.float32)
    vec_b[1] = 1.0
    p1 = ex("INSERT INTO people(name, created_ts, hidden) VALUES('Ada', 1, 0)")
    f1 = ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.3,0.3,0.95,?,?)", (ids[0], vec_a.tobytes(), p1))
    f2 = ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.3,0.3,0.9,?,?)", (ids[1], vec_b.tobytes(), p1))

    res = client.patch(f"/api/faces/{f2}/person", json={"person_id": None, "new_name": "Bea"}, headers=HEADERS).json()
    new_pid = res["person_id"]
    assert new_pid != p1
    people = {p["name"]: p for p in client.get("/api/people").json()["people"]}
    assert people["Ada"]["faces"] == 1 and people["Bea"]["faces"] == 1

    res = client.post("/api/people/rebuild", json={"threshold": 0.5}, headers=HEADERS).json()
    assert res["faces_assigned"] == 2 and res["people"] == 2
    assert client.get("/api/people/threshold").json()["threshold"] == 0.5
    same = client.post("/api/people/rebuild", json={"threshold": 0.3}, headers=HEADERS).json()
    assert same["people"] == 2

    res = client.patch(f"/api/faces/{f1}/person", json={"person_id": None, "new_name": "Solo"}, headers=HEADERS)
    assert res.status_code == 200


def test_search_scopes(client, tmp_path):
    from app.db import ex

    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "receipt.jpg", "JPEG")
    import_dir(client, src)
    mid = client.get("/api/media").json()["items"][0]["id"]
    ex("UPDATE media SET ocr_text='total amount due tonight' WHERE id=?", (mid,))

    assert client.get("/api/media/search", params={"q": "tonight", "fields": "name"}).json()["items"] == []
    hit = client.get("/api/media/search", params={"q": "tonight", "fields": "ocr"}).json()
    assert [m["id"] for m in hit["items"]] == [mid] and hit["fields"] == ["ocr"]
    assert client.get("/api/media/search", params={"q": "receipt", "fields": "name"}).json()["items"][0]["id"] == mid
