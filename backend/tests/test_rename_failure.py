import os

from tests.conftest import HEADERS, import_dir, pattern


def import_three(client, tmp_path):
    from app.db import q

    src = tmp_path / "src"
    os.makedirs(src)
    for index in range(3):
        pattern(64 + index, 48).save(src / f"p{index}.jpg", "JPEG")
    import_dir(client, src)
    return q("SELECT id, name, rel_path FROM media ORDER BY id")


def names():
    from app.db import q

    return {r["id"]: r["name"] for r in q("SELECT id, name FROM media")}


def test_a_file_missing_from_disk_is_reported_and_the_others_are_renamed(client, tmp_path):
    from app.services import libraryfs

    rows = import_three(client, tmp_path)
    os.unlink(libraryfs.abs_path(rows[1]["rel_path"]))
    ids = [r["id"] for r in rows]
    answer = client.post("/api/media/rename", json={"ids": ids, "template": "new_{seq:2}"}, headers=HEADERS)
    assert answer.status_code == 200
    plan = {p["id"]: p for p in answer.json()["plan"]}
    assert [plan[i]["ok"] for i in ids] == [True, False, True]
    assert plan[ids[1]]["reason"] == "The file could not be renamed"
    after = names()
    assert after[ids[0]] == "new_01.jpg"
    assert after[ids[1]] == rows[1]["name"]
    assert after[ids[2]] == "new_03.jpg"
    folder = os.path.dirname(libraryfs.abs_path(rows[0]["rel_path"]))
    assert "new_01.jpg" in os.listdir(folder) and "new_03.jpg" in os.listdir(folder)


def test_a_sidecar_that_cannot_move_does_not_leave_the_catalog_behind(client, tmp_path, monkeypatch):
    from app.services import libraryfs

    rows = import_three(client, tmp_path)[:1]
    path = libraryfs.abs_path(rows[0]["rel_path"])
    with open(path + ".xmp", "w") as handle:
        handle.write("<x/>")
    real = os.rename

    def rename(source, target):
        if str(source).endswith(".xmp"):
            raise PermissionError(13, "denied", str(source))
        return real(source, target)

    monkeypatch.setattr(os, "rename", rename)
    answer = client.post("/api/media/rename", json={"ids": [rows[0]["id"]], "template": "z{seq:2}"}, headers=HEADERS)
    assert answer.status_code == 200
    assert answer.json()["plan"][0]["ok"] is True
    assert names()[rows[0]["id"]] == "z01.jpg"
    assert os.path.isfile(os.path.join(os.path.dirname(path), "z01.jpg"))
