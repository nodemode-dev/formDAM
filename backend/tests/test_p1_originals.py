import os

from tests.conftest import HEADERS, import_dir, pattern
from tests.support import sha, tree_hashes


def make_source(tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    pattern(400, 300).save(src / "one.jpg", "JPEG", quality=90)
    pattern(300, 400, "v").save(src / "two.jpg", "JPEG", quality=90)
    return src


def library_copy(client, media_id):
    from app.services.libraryfs import abs_path

    return abs_path(client.get(f"/api/media/{media_id}").json()["rel_path"])


def test_ingest_leaves_the_source_files_untouched(client, tmp_path):
    src = make_source(tmp_path)
    before = tree_hashes(src)
    counts = import_dir(client, src)
    assert counts["imported"] == 2
    assert tree_hashes(src) == before


def test_library_copy_is_byte_identical_to_the_source(client, tmp_path):
    src = make_source(tmp_path)
    import_dir(client, src)
    sources = {sha(src / name) for name in os.listdir(src)}
    copies = {sha(library_copy(client, m["id"])) for m in client.get("/api/media").json()["items"]}
    assert copies == sources


def test_edits_never_change_source_or_library_copy(client, tmp_path):
    src = make_source(tmp_path)
    import_dir(client, src)
    before_src = tree_hashes(src)
    item = client.get("/api/media").json()["items"][0]
    stored = library_copy(client, item["id"])
    before_copy = sha(stored)
    state = {"light": {"exposure": 0.8, "contrast": 20}, "bw": {"on": True}}
    put = client.put(f"/api/media/{item['id']}/edits", json={"state": state}, headers=HEADERS)
    assert put.status_code == 200 and put.json()["edit_json"]
    assert client.post(f"/api/media/{item['id']}/preview", json={"state": state, "w": 256}, headers=HEADERS).status_code == 200
    assert client.get(f"/api/media/{item['id']}/render", params={"w": 200}).status_code in (200, 404)
    assert sha(stored) == before_copy
    assert client.delete(f"/api/media/{item['id']}/edits", headers=HEADERS).status_code == 200
    assert sha(stored) == before_copy
    assert tree_hashes(src) == before_src


def test_batch_edit_and_metadata_writes_leave_originals_alone(client, tmp_path):
    src = make_source(tmp_path)
    import_dir(client, src)
    ids = [m["id"] for m in client.get("/api/media").json()["items"]]
    copies = {i: library_copy(client, i) for i in ids}
    before = {i: sha(p) for i, p in copies.items()}
    assert client.post("/api/media/batch/edits", json={"ids": ids, "state": {"light": {"exposure": 0.3}}}, headers=HEADERS).status_code == 200
    assert client.post("/api/fileinfo", json={"ids": ids, "fields": {"creator": "Test", "title": "T"}}, headers=HEADERS).status_code == 200
    assert client.patch(f"/api/media/{ids[0]}/meta", json={"rating": 4}, headers=HEADERS).status_code == 200
    assert {i: sha(p) for i, p in copies.items()} == before


def test_delete_from_library_never_touches_the_source(client, tmp_path):
    src = make_source(tmp_path)
    import_dir(client, src)
    before = tree_hashes(src)
    token = client.post("/api/vault/setup", json={"passkey": "originalskey"}, headers=HEADERS).json()["token"]
    auth = {**HEADERS, "x-dam-vault": token}
    for item in client.get("/api/media").json()["items"]:
        assert client.post(f"/api/media/{item['id']}/trash", headers=HEADERS).status_code == 200
        assert client.delete(f"/api/trash/{item['id']}", headers=auth).status_code == 200
    assert client.get("/api/media").json()["items"] == []
    assert tree_hashes(src) == before


def test_referenced_original_survives_delete_forever(client, tmp_path):
    src = make_source(tmp_path)
    before = tree_hashes(src)
    created = client.post("/api/import", json={"path": str(src), "reference": True}, headers=HEADERS)
    assert created.status_code == 202
    from tests.conftest import wait_job

    assert wait_job(client, created.json()["job_id"])["phase"] == "done"
    items = client.get("/api/media").json()["items"]
    assert len(items) == 2
    token = client.post("/api/vault/setup", json={"passkey": "referencekey"}, headers=HEADERS).json()["token"]
    auth = {**HEADERS, "x-dam-vault": token}
    for item in items:
        client.post(f"/api/media/{item['id']}/trash", headers=HEADERS)
        client.delete(f"/api/trash/{item['id']}", headers=auth)
    assert tree_hashes(src) == before


def test_same_file_twice_is_deduplicated_by_hash(client, tmp_path):
    src = make_source(tmp_path)
    first = import_dir(client, src)
    again = import_dir(client, src)
    assert first["imported"] == 2
    assert again["imported"] == 0 and again["duplicates"] == 2
    assert len(client.get("/api/media").json()["items"]) == 2


def test_renamed_copy_of_the_same_bytes_is_a_duplicate(client, tmp_path):
    src = make_source(tmp_path)
    import_dir(client, src)
    other = tmp_path / "other"
    os.makedirs(other)
    (other / "renamed.jpg").write_bytes((src / "one.jpg").read_bytes())
    counts = import_dir(client, other)
    assert counts["imported"] == 0 and counts["duplicates"] == 1
    assert len(client.get("/api/media").json()["items"]) == 2


def test_library_holds_one_file_per_distinct_hash(client, tmp_path):
    src = make_source(tmp_path)
    import_dir(client, src)
    import_dir(client, src)
    from app.config import originals_dir

    stored = [os.path.join(b, n) for b, _, names in os.walk(originals_dir()) for n in names]
    assert len(stored) == 2 and len({sha(p) for p in stored}) == 2
