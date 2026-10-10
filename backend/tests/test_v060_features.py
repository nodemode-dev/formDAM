import os

from tests.conftest import HEADERS, import_dir, pattern


def _two(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src, exist_ok=True)
    pattern(320, 240).save(src / "a.jpg", "JPEG")
    pattern(240, 320, "v").save(src / "b.jpg", "JPEG")
    import_dir(client, src)
    return [m["id"] for m in client.get("/api/media").json()["items"]]


def test_hidden_media_stays_out_of_person_pages(client, tmp_path):
    import numpy as np

    from app.db import ex

    ids = _two(client, tmp_path)
    emb = np.ones(128, dtype=np.float32).tobytes()
    pid = ex("INSERT INTO people(name, created_ts, hidden) VALUES('Ada', 1, 0)")
    for mid in ids:
        ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.3,0.3,0.9,?,?)", (mid, emb, pid))

    client.post(f"/api/media/{ids[0]}/hide", headers=HEADERS)
    detail = client.get(f"/api/people/{pid}").json()
    assert [m["id"] for m in detail["items"]] == [ids[1]]
    stats = client.get("/api/people").json()["people"][0]
    assert stats["media"] == 1
    face_media = {f["media_id"] for f in client.get(f"/api/people/{pid}/faces").json()["faces"]}
    assert face_media == {ids[1]}


def test_rebuild_preserves_manual_names(client, tmp_path):
    import numpy as np

    from app.db import ex

    ids = _two(client, tmp_path)
    vec_a = np.zeros(128, dtype=np.float32)
    vec_a[0] = 1.0
    vec_b = np.zeros(128, dtype=np.float32)
    vec_b[3] = 1.0
    ada = ex("INSERT INTO people(name, created_ts, hidden) VALUES('Ada', 1, 0)")
    ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.3,0.3,0.95,?,?)", (ids[0], vec_a.tobytes(), ada))
    anon = ex("INSERT INTO people(name, created_ts, hidden) VALUES(NULL, 1, 0)")
    ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.3,0.3,0.9,?,?)", (ids[1], vec_b.tobytes(), anon))

    res = client.post("/api/people/rebuild", json={"threshold": 0.5}, headers=HEADERS).json()
    assert res["named_preserved"] == 1
    people = client.get("/api/people").json()["people"]
    named = [p for p in people if p["name"] == "Ada"]
    assert len(named) == 1 and named[0]["id"] == ada and named[0]["faces"] == 1


def test_reassign_media_moves_face_crops(client, tmp_path):
    import numpy as np

    from app.db import ex

    ids = _two(client, tmp_path)
    emb = np.ones(128, dtype=np.float32).tobytes()
    src_p = ex("INSERT INTO people(name, created_ts, hidden) VALUES('Mixed', 1, 0)")
    for mid in ids:
        ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.3,0.3,0.9,?,?)", (mid, emb, src_p))

    res = client.post(f"/api/people/{src_p}/reassign-media",
                      json={"media_ids": [ids[0]], "new_name": "Bea"}, headers=HEADERS).json()
    assert res["moved_faces"] == 1
    people = {p["name"]: p for p in client.get("/api/people").json()["people"]}
    assert people["Mixed"]["media"] == 1 and people["Bea"]["media"] == 1


def test_album_manual_order(client, tmp_path):
    ids = _two(client, tmp_path)
    album = client.post("/api/albums", json={"name": "Trip"}, headers=HEADERS).json()
    client.post(f"/api/albums/{album['id']}/items", json={"media_ids": ids}, headers=HEADERS)
    client.put(f"/api/albums/{album['id']}/order", json={"media_ids": list(reversed(ids))}, headers=HEADERS)
    detail = client.get(f"/api/albums/{album['id']}").json()
    assert [m["id"] for m in detail["items"]] == list(reversed(ids))


def test_library_oldest_order(client, tmp_path):
    ids = _two(client, tmp_path)
    newest = client.get("/api/media").json()["items"]
    oldest = client.get("/api/media", params={"order": "oldest"}).json()["items"]
    assert [m["id"] for m in oldest] == [m["id"] for m in reversed(newest)]
    assert set(m["id"] for m in newest) == set(ids)


def test_health_reports_ffmpeg_and_video_placeholder(client, tmp_path):
    from app.db import ex, q1
    from app.services import thumbs

    assert "ffmpeg" in client.get("/api/health").json()
    ids = _two(client, tmp_path)
    row = q1("SELECT rel_path FROM media WHERE id=?", (ids[0],))
    ex("UPDATE media SET kind='video', mime='video/mp4' WHERE id=?", (ids[0],))
    poster = thumbs.ensure_thumb(ids[0], row["rel_path"], "video", 384)
    assert poster and os.path.getsize(poster) > 0


def test_person_cover_lock(client, tmp_path):
    import numpy as np

    from app.db import ex, q1
    from app.services import facesvc

    ids = _two(client, tmp_path)
    emb = np.ones(128, dtype=np.float32).tobytes()
    pid = ex("INSERT INTO people(name, created_ts, hidden) VALUES('Ada', 1, 0)")
    for mid in ids:
        ex("INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,0,0.1,0.1,0.3,0.3,0.9,?,?)", (mid, emb, pid))

    other = client.post(f"/api/people/{pid}/cover", json={"media_id": 999999}, headers=HEADERS)
    assert other.status_code == 400
    ok = client.post(f"/api/people/{pid}/cover", json={"media_id": ids[1]}, headers=HEADERS)
    assert ok.status_code == 200
    facesvc.refresh_cover(pid)
    cover_face = q1("SELECT cover_face_id FROM people WHERE id=?", (pid,))["cover_face_id"]
    assert q1("SELECT media_id FROM faces WHERE id=?", (cover_face,))["media_id"] == ids[1]
    client.delete(f"/api/people/{pid}/cover", headers=HEADERS)
    assert q1("SELECT cover_locked FROM people WHERE id=?", (pid,))["cover_locked"] == 0
