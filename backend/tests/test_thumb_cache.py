import os

from tests.conftest import HEADERS, import_dir, pattern


def one_item(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(320, 240).save(src / "one.jpg", "JPEG")
    import_dir(client, src)
    return client.get("/api/media").json()["items"][0]["id"]


def test_a_thumbnail_is_revalidated_so_hiding_it_takes_effect_at_once(client, tmp_path):
    media_id = one_item(client, tmp_path)
    url = f"/api/media/{media_id}/thumb?s=384"
    first = client.get(url)
    assert first.status_code == 200
    assert "no-cache" in first.headers["cache-control"]
    assert "max-age=604800" not in first.headers["cache-control"]
    etag = first.headers["etag"]
    again = client.get(url, headers={"if-none-match": etag})
    assert again.status_code == 304
    assert client.post(f"/api/media/{media_id}/hide", headers=HEADERS).status_code == 200
    assert client.get(url, headers={"if-none-match": etag}).status_code == 401

