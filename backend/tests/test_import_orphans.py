import json
import os

from tests.conftest import HEADERS, pattern, wait_job


def orphan_files(tmp_path):
    from app.services import libraryfs

    folder = os.path.join(libraryfs.originals_dir(), "2026", "01")
    os.makedirs(folder)
    paths = []
    for index, size in enumerate((40, 50, 60)):
        path = os.path.join(folder, f"orphan{index}.jpg")
        pattern(size, 30).save(path, "JPEG")
        paths.append(path)
    return paths


def report(paths):
    from app.db import setting_set

    setting_set("repair_report", json.dumps({"orphans": paths}))


def names():
    from app.db import q

    return sorted(r["name"] for r in q("SELECT name FROM media"))


def test_import_orphans_imports_every_unknown_file(client, tmp_path):
    report(orphan_files(tmp_path))
    job = client.post("/api/library/import-orphans", headers=HEADERS).json()["job_id"]
    state = wait_job(client, job)
    assert state["phase"] == "done"
    assert state["counts"] == {"imported": 3, "duplicates": 0, "failed": 0}
    assert names() == ["orphan0.jpg", "orphan1.jpg", "orphan2.jpg"]


def test_one_file_that_cannot_be_imported_does_not_stop_the_others(client, tmp_path, monkeypatch):
    from app.services import libraryfs

    report(orphan_files(tmp_path))
    real = libraryfs.import_one

    def import_one(path, **kwargs):
        if path.endswith("orphan1.jpg"):
            raise PermissionError(13, "denied", path)
        return real(path, **kwargs)

    monkeypatch.setattr(libraryfs, "import_one", import_one)
    job = client.post("/api/library/import-orphans", headers=HEADERS).json()["job_id"]
    state = wait_job(client, job)
    assert state["phase"] == "done"
    assert state["counts"] == {"imported": 2, "duplicates": 0, "failed": 1}
    assert names() == ["orphan0.jpg", "orphan2.jpg"]
