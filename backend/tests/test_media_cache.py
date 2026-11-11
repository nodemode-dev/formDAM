import os

import pytest

from tests.conftest import HEADERS, pattern
from tests.test_thumb_cache import one_item

ROUTES = ("thumb?s=384", "render?w=640", "file")


def vault_auth(client):
    token = client.post("/api/vault/setup", json={"passkey": "rootkey9"}, headers=HEADERS).json()["token"]
    return {**HEADERS, "x-dam-vault": token}


@pytest.mark.parametrize("route", ROUTES)
def test_a_shown_item_is_revalidated_on_every_byte_route(client, tmp_path, route):
    media_id = one_item(client, tmp_path)
    url = f"/api/media/{media_id}/{route}"
    first = client.get(url)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "private, no-cache"
    etag = first.headers["etag"]
    again = client.get(url, headers={"if-none-match": etag})
    assert again.status_code == 304
    assert again.headers["cache-control"] == "private, no-cache"
    assert client.post(f"/api/media/{media_id}/hide", headers=HEADERS).status_code == 200
    assert client.get(url, headers={"if-none-match": etag}).status_code == 401


@pytest.mark.parametrize("route", ROUTES)
def test_a_hidden_item_is_never_stored_while_the_vault_is_open(client, tmp_path, route):
    media_id = one_item(client, tmp_path)
    auth = vault_auth(client)
    assert client.post(f"/api/media/{media_id}/hide", headers=HEADERS).status_code == 200
    url = f"/api/media/{media_id}/{route}"
    seen = client.get(url, headers=auth)
    assert seen.status_code == 200
    assert seen.headers["cache-control"] == "no-store"
    assert "etag" not in seen.headers


def test_a_cached_render_is_revalidated_too(client, tmp_path):
    media_id = one_item(client, tmp_path)
    url = f"/api/media/{media_id}/render?w=640"
    assert client.get(url).status_code == 200
    cached = client.get(url)
    assert cached.headers["cache-control"] == "private, no-cache"
    assert client.get(url, headers={"if-none-match": cached.headers["etag"]}).status_code == 304


def test_a_ranged_original_carries_the_tag_and_still_streams(client, tmp_path):
    media_id = one_item(client, tmp_path)
    url = f"/api/media/{media_id}/file"
    tag = client.get(url).headers["etag"]
    part = client.get(url, headers={"range": "bytes=0-9", "if-none-match": tag})
    assert part.status_code == 206
    assert part.headers["etag"] == tag
    assert part.headers["cache-control"] == "private, no-cache"


def face_of(client, tmp_path, monkeypatch):
    media_id = one_item(client, tmp_path)
    from app.db import ex
    from app.services import facesvc

    face_id = ex("INSERT INTO faces(media_id, x, y, w, h, embedding) VALUES (?, 0.1, 0.1, 0.2, 0.2, ?)", (media_id, b"\0"))
    crop = tmp_path / "crop.jpg"
    pattern(64, 64).save(crop, "JPEG")
    monkeypatch.setattr(facesvc, "face_crop", lambda _face: os.fspath(crop))
    return media_id, face_id


def test_a_face_crop_is_revalidated_and_stops_being_stored_once_hidden(client, tmp_path, monkeypatch):
    media_id, face_id = face_of(client, tmp_path, monkeypatch)
    url = f"/api/faces/{face_id}/thumb"
    first = client.get(url)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "private, no-cache"
    assert client.get(url, headers={"if-none-match": first.headers["etag"]}).status_code == 304
    auth = vault_auth(client)
    assert client.post(f"/api/media/{media_id}/hide", headers=HEADERS).status_code == 200
    hidden = client.get(url, headers=auth)
    assert hidden.headers["cache-control"] == "no-store"
    assert "etag" not in hidden.headers
