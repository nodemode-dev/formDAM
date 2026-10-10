import os

from tests.conftest import HEADERS, import_dir, pattern


def test_health_and_version(client):
    from app.config import VERSION
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["version"] == VERSION


def test_import_grid_filters_and_files(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(400, 300).save(src / "photo-a.jpg", "JPEG", quality=90)
    pattern(400, 300).save(src / "photo-a-copy.jpg", "JPEG", quality=90)
    pattern(300, 400, "v").save(src / "Screenshot 2026-07-25.png", "PNG")

    counts = import_dir(client, src)
    assert counts == {"found": 3, "imported": 2, "duplicates": 1, "skipped": 0, "failed": 0}

    listing = client.get("/api/media").json()
    assert len(listing["items"]) == 2
    shots = client.get("/api/media", params={"filter": "screenshots"}).json()["items"]
    assert len(shots) == 1 and shots[0]["is_screenshot"] is True

    media_id = listing["items"][0]["id"]
    assert client.post(f"/api/media/{media_id}/favorite", json={"on": True}, headers=HEADERS).status_code == 200
    favs = client.get("/api/media", params={"filter": "favorites"}).json()["items"]
    assert [m["id"] for m in favs] == [media_id]

    assert client.post(f"/api/media/{media_id}/viewed", headers=HEADERS).status_code == 200
    viewed = client.get("/api/media", params={"filter": "recently_viewed"}).json()["items"]
    assert viewed and viewed[0]["id"] == media_id

    thumb = client.get(f"/api/media/{media_id}/thumb", params={"s": 200})
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"

    ranged = client.get(f"/api/media/{media_id}/file", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206
    assert len(ranged.content) == 100
    assert ranged.headers["content-range"].startswith("bytes 0-99/")

    summary = client.get("/api/summary").json()
    assert summary["total"] == 2 and summary["screenshots"] == 1

    months = client.get("/api/media/summary", params={"level": "month"}).json()
    assert months["periods"] and months["periods"][0]["count"] >= 1


def test_remote_and_missing_header_rejected(client, tmp_path):
    from app.main import app
    from starlette.testclient import TestClient
    with TestClient(app, base_url="http://127.0.0.1", client=("10.0.0.9", 4444)) as remote:
        assert remote.get("/api/health").status_code == 403
    assert client.post("/api/import", json={"path": str(tmp_path)}).status_code == 403
