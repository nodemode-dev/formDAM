import os

import pytest

from tests.conftest import HEADERS, import_dir, pattern, wait_job

IPTC = {
    "headline": "Head line", "creator": "A. Maker", "creatorJob": "Photographer", "creatorAddress": "1 Test St",
    "creatorCity": "Testville", "creatorState": "TS", "creatorCountry": "Testland", "creatorEmail": "a@example.test",
    "creatorPhone": "+1 555 0100", "creatorUrl": "https://example.test", "copyright": "(c) 2026 A. Maker",
    "copyrightStatus": "Copyrighted", "rightsUsage": "Editorial use", "copyrightUrl": "https://example.test/rights",
    "sublocation": "Old Town", "city": "Testville", "state": "TS", "country": "Testland", "isoCountryCode": "TL",
    "jobId": "JOB-7", "instructions": "Embargo none", "credit": "Credit Line", "source": "Source Line",
    "intellectualGenre": "Feature", "scene": "010000, 020000", "subjectCode": "01001000", "event": "Test Event",
    "personShown": "Ann, Bob", "extendedDescription": "Long accessible text",
    "title": "A title", "caption": "A caption", "altText": "Alt words",
}


def record():
    return {"rating": 4, "label": "red", "favorite": True, "captureTime": "2026-03-04T05:06:07",
            "keywords": ["Places|Paris", "Pets"], "meta": dict(IPTC)}


def test_the_field_table_in_the_test_covers_every_engine_field():
    from app.services import xmpsvc

    assert set(xmpsvc.FIELDS) | {"title", "caption", "altText"} == set(IPTC)


def test_build_then_parse_keeps_every_field():
    from app.services import xmpsvc

    parsed = xmpsvc.parse_xmp(xmpsvc.build_xmp(record()))
    assert parsed["meta"] == IPTC
    assert parsed["rating"] == 4 and parsed["label"] == "Red" and parsed["favorite"] is True
    assert sorted(parsed["keywords"]) == ["Pets", "Places|Paris"]


@pytest.mark.parametrize("text", ["A & B <tag> \"quoted\" 'single'", "Zoe's café – 日本"])
def test_special_characters_survive_the_round_trip(text):
    from app.services import xmpsvc

    rec = {"rating": 0, "meta": {"headline": text, "caption": text, "creator": text}}
    meta = xmpsvc.parse_xmp(xmpsvc.build_xmp(rec))["meta"]
    assert meta == {"headline": text, "caption": text, "creator": text}


def test_rejected_rating_round_trips_as_minus_one():
    from app.services import xmpsvc

    assert xmpsvc.parse_xmp(xmpsvc.build_xmp({"rating": -1}))["rating"] == -1


@pytest.fixture
def one_photo(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(400, 300).save(src / "shot.jpg", "JPEG", quality=90)
    import_dir(client, src)
    return client.get("/api/media").json()["items"][0]["id"]


def stored_fields(client, media_id):
    return client.post("/api/fileinfo/common", json={"ids": [media_id]}, headers=HEADERS).json()["fields"]


def test_sidecar_written_by_the_engine_restores_every_field_after_a_wipe(client, one_photo):
    from app.services import xmpsvc

    saved = client.post("/api/fileinfo", json={"ids": [one_photo], "fields": IPTC}, headers=HEADERS)
    assert saved.status_code == 200
    client.patch(f"/api/media/{one_photo}/meta", json={"rating": 3, "label": "blue"}, headers=HEADERS)
    keywords = client.post("/api/media/keywords", json={"ids": [one_photo], "add": ["Trips"]}, headers=HEADERS)
    assert keywords.status_code == 200
    expected = stored_fields(client, one_photo)
    assert all(expected.get(k) == v for k, v in IPTC.items())
    job = client.post("/api/xmp/write", json={"ids": [one_photo]}, headers=HEADERS).json()["job_id"]
    assert wait_job(client, job)["counts"]["written"] == 1
    from app.db import q1
    from app.services import libraryfs

    path = libraryfs.abs_path(q1("SELECT rel_path FROM media WHERE id=?", (one_photo,))["rel_path"])
    assert os.path.isfile(xmpsvc.sidecar_for(path))
    client.post("/api/fileinfo", json={"ids": [one_photo], "fields": {k: "" for k in IPTC}}, headers=HEADERS)
    assert stored_fields(client, one_photo).get("headline", "") == ""
    assert client.post("/api/xmp/read", json={"ids": [one_photo]}, headers=HEADERS).json() == {"read": 1}
    assert stored_fields(client, one_photo) == expected
    row = client.get(f"/api/media/{one_photo}").json()
    assert row["rating"] == 3 and row["label"] == "blue"
