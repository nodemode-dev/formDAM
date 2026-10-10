import io
import time

from tests.conftest import HEADERS, pattern


class FakeAfc:
    def __init__(self, files):
        self.files = files

    def listdir(self, path):
        if path == "/DCIM":
            return ["100APPLE"]
        if path == "/DCIM/100APPLE":
            return sorted({name.split("/")[-1] for name in self.files})
        return []

    def get_file_contents(self, remote):
        return self.files[remote]


def _fake_bytes(tag):
    buf = io.BytesIO()
    pattern(200 if tag == "a" else 240, 160, tag).save(buf, "JPEG")
    return buf.getvalue()


def test_idevice_import_roundtrip(client, monkeypatch):
    from app.services import idevicesvc

    files = {
        "/DCIM/100APPLE/IMG_0001.JPG": _fake_bytes("a"),
        "/DCIM/100APPLE/IMG_0002.JPG": _fake_bytes("b"),
    }
    monkeypatch.setattr(idevicesvc, "_list_factory", lambda: [type("D", (), {"serial": "TESTSERIAL"})()])
    monkeypatch.setattr(idevicesvc, "_lockdown_factory", lambda serial: type("L", (), {"all_values": {"DeviceName": "Test iPhone"}})())
    monkeypatch.setattr(idevicesvc, "_afc_factory", lambda lockdown: FakeAfc(files))

    assert client.get("/api/idevice/status").json()["supported"] is True
    devices = client.get("/api/idevice/devices").json()["devices"]
    assert devices == [{"serial": "TESTSERIAL", "name": "Test iPhone", "state": "ready", "via": "afc"}]

    job = client.post("/api/idevice/import", json={"serial": "TESTSERIAL"}, headers=HEADERS).json()
    for _ in range(100):
        state = client.get(f"/api/jobs/{job['job_id']}").json()
        if state.get("phase") in ("done", "error"):
            break
        time.sleep(0.05)
    assert state.get("phase") == "done"
    assert state["counts"]["imported"] == 2 and state["counts"]["failed"] == 0

    items = client.get("/api/media").json()["items"]
    assert len(items) == 2

    job2 = client.post("/api/idevice/import", json={"serial": "TESTSERIAL"}, headers=HEADERS).json()
    for _ in range(100):
        state2 = client.get(f"/api/jobs/{job2['job_id']}").json()
        if state2.get("phase") in ("done", "error"):
            break
        time.sleep(0.05)
    assert state2["counts"]["duplicates"] == 2 and state2["counts"]["imported"] == 0


def test_drop_upload_import(client):
    a = _fake_bytes("a")
    b = _fake_bytes("b")
    res = client.post(
        "/api/import/upload",
        files=[
            ("files", ("drop_a.jpg", a, "image/jpeg")),
            ("files", ("drop_b.jpg", b, "image/jpeg")),
            ("files", ("notes.txt", b"hello", "text/plain")),
        ],
        headers=HEADERS,
    )
    assert res.status_code == 200
    counts = res.json()["counts"]
    assert counts["imported"] == 2 and counts["skipped"] == 1
    again = client.post(
        "/api/import/upload",
        files=[("files", ("drop_a.jpg", a, "image/jpeg"))],
        headers=HEADERS,
    ).json()["counts"]
    assert again["duplicates"] == 1 and again["imported"] == 0


def test_import_multiple_paths_one_job(client, tmp_path):
    import os
    import time

    a = tmp_path / "a"
    b = tmp_path / "b"
    os.makedirs(a)
    os.makedirs(b)
    (a / "one.jpg").write_bytes(_fake_bytes("a"))
    (b / "two.jpg").write_bytes(_fake_bytes("b"))
    job = client.post("/api/import", json={"path": str(a), "paths": [str(a), str(b)]}, headers=HEADERS).json()
    for _ in range(100):
        state = client.get(f"/api/jobs/{job['job_id']}").json()
        if state.get("phase") in ("done", "error"):
            break
        time.sleep(0.05)
    assert state["phase"] == "done" and state["counts"]["imported"] == 2


def test_menubar_pref_roundtrip(client):
    assert client.get("/api/system/menubar").json() == {"enabled": False}
    client.post("/api/system/menubar", json={"enabled": True}, headers=HEADERS)
    assert client.get("/api/system/menubar").json() == {"enabled": True}
