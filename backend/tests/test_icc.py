import io
import os

import pytest

from tests.conftest import HEADERS, pattern, wait_job

THUMB = b"\xff\xd8fakejpeg"


class FakeBridge:
    def __init__(self, files, restricted=False, extras=None):
        self.files = files
        self.extras = extras or {}
        self.restricted = restricted
        self.opened = 0
        self.closed = 0
        self.gen = 0
        self.deleted = []
        self.session_open = False

    def start(self):
        pass

    def devices(self):
        return [{"serial": "ICC-UUID-1", "name": "Fake iPhone", "restricted": self.restricted}]

    def open_session(self, serial, timeout):
        from app.services import iccsvc

        if self.restricted:
            raise RuntimeError(iccsvc.LOCKED_GUIDANCE)
        if not self.session_open:
            self.session_open = True
            self.opened += 1

    def wait_ready(self, serial, timeout):
        pass

    def _names(self):
        return sorted(self.files)

    def media_files(self, serial):
        self.gen += 1
        files = [
            {"key": i, "name": name, "size": len(self.files[name]), "date": 1700000000.0 + i, "duration": None}
            for i, name in enumerate(self._names())
        ]
        self._meta = files
        return {"gen": self.gen, "files": files}

    def listing_for(self, serial, gen):
        if gen != self.gen:
            raise RuntimeError("The device contents changed; reopen the device & retry.")
        return list(self._meta)

    def thumbnail(self, serial, key, gen, timeout):
        if gen != self.gen or key >= len(self._names()):
            return None
        return THUMB

    def download(self, serial, key, gen, dest_dir, timeout):
        if gen != self.gen:
            raise RuntimeError("The device contents changed; reopen the device & retry.")
        name = self._names()[key]
        path = os.path.join(dest_dir, name)
        with open(path, "wb") as handle:
            handle.write(self.files[name])
        extras = []
        for extra_name, blob in self.extras.get(name, []):
            extra_path = os.path.join(dest_dir, extra_name)
            with open(extra_path, "wb") as handle:
                handle.write(blob)
            extras.append(extra_name)
        return {"path": path, "extras": extras}

    def delete_files(self, serial, keys, gen, timeout):
        if gen != self.gen:
            return "The device contents changed; nothing was deleted."
        self.deleted.extend(keys)
        return ""

    def close_session(self, serial):
        self.session_open = False
        self.closed += 1


def _jpeg(tag):
    buf = io.BytesIO()
    pattern(220 if tag == "a" else 250, 170, tag).save(buf, "JPEG")
    return buf.getvalue()


def _mp4_bytes():
    return b"\x00\x00\x00\x18ftypmp42" + os.urandom(2048)


@pytest.fixture
def icc_reset():
    from app.services import iccsvc

    iccsvc.reset_for_tests()
    yield iccsvc
    iccsvc._bridge_factory = None
    iccsvc.reset_for_tests()


def _install(icc_reset, bridge):
    icc_reset._bridge_factory = lambda: bridge
    return bridge


def test_icc_import_roundtrip(client, icc_reset):
    bridge = _install(icc_reset, FakeBridge({"IMG_9001.JPG": _jpeg("a"), "IMG_9002.JPG": _jpeg("b")}))

    status = client.get("/api/idevice/status").json()
    assert status["supported"] is True
    assert "native" in status and "afc" in status and "platform" in status

    devices = client.get("/api/idevice/devices").json()["devices"]
    assert {"serial": "ICC-UUID-1", "name": "Fake iPhone", "state": "ready", "via": "icc"} in devices

    job = client.post("/api/idevice/import", json={"serial": "ICC-UUID-1"}, headers=HEADERS).json()
    state = wait_job(client, job["job_id"])
    assert state["phase"] == "done", state
    assert state["counts"]["found"] == 2
    assert state["counts"]["imported"] == 2 and state["counts"]["failed"] == 0
    assert bridge.opened == 1 and bridge.deleted == []
    assert len(client.get("/api/media").json()["items"]) == 2

    again = client.post("/api/idevice/import", json={"serial": "ICC-UUID-1"}, headers=HEADERS).json()
    state2 = wait_job(client, again["job_id"])
    assert state2["counts"]["duplicates"] == 2 and state2["counts"]["imported"] == 0


def test_icc_contents_thumb_and_selective_import(client, icc_reset):
    bridge = _install(icc_reset, FakeBridge({"IMG_0001.JPG": _jpeg("a"), "IMG_0002.JPG": _jpeg("b"), "CLIP_0003.MP4": _mp4_bytes()}))

    listing = client.post("/api/idevice/contents", json={"serial": "ICC-UUID-1"}, headers=HEADERS).json()
    assert listing["gen"] == 1
    names = [f["name"] for f in listing["files"]]
    assert names == ["CLIP_0003.MP4", "IMG_0001.JPG", "IMG_0002.JPG"]
    kinds = {f["name"]: f["kind"] for f in listing["files"]}
    assert kinds["CLIP_0003.MP4"] == "video" and kinds["IMG_0001.JPG"] == "image"

    thumb = client.get("/api/idevice/thumb", params={"serial": "ICC-UUID-1", "key": 1, "gen": 1})
    assert thumb.status_code == 200 and thumb.content == THUMB
    missing = client.get("/api/idevice/thumb", params={"serial": "ICC-UUID-1", "key": 1, "gen": 99})
    assert missing.status_code == 404

    picked = [f["key"] for f in listing["files"] if f["name"] == "IMG_0002.JPG"]
    job = client.post(
        "/api/idevice/import",
        json={"serial": "ICC-UUID-1", "keys": picked, "gen": listing["gen"]},
        headers=HEADERS,
    ).json()
    state = wait_job(client, job["job_id"])
    assert state["phase"] == "done", state
    assert state["counts"]["found"] == 1 and state["counts"]["imported"] == 1
    items = client.get("/api/media").json()["items"]
    assert [item["name"] for item in items] == ["IMG_0002.JPG"]

    stale = client.post(
        "/api/idevice/import",
        json={"serial": "ICC-UUID-1", "keys": picked, "gen": 99},
        headers=HEADERS,
    ).json()
    assert wait_job(client, stale["job_id"])["phase"] == "error"

    closed = client.post("/api/idevice/session/close", json={"serial": "ICC-UUID-1"}, headers=HEADERS).json()
    assert closed["ok"] is True and bridge.closed == 1


def test_icc_delete_after_only_on_success(client, icc_reset):
    bridge = _install(icc_reset, FakeBridge({"IMG_0001.JPG": _jpeg("a"), "BAD_0002.JPG": b"not-a-real-image-but-imports-fine"}))

    listing = client.post("/api/idevice/contents", json={"serial": "ICC-UUID-1"}, headers=HEADERS).json()
    job = client.post(
        "/api/idevice/import",
        json={"serial": "ICC-UUID-1", "gen": listing["gen"], "delete_after": True},
        headers=HEADERS,
    ).json()
    state = wait_job(client, job["job_id"])
    assert state["phase"] == "done", state
    assert state["counts"]["imported"] == 2
    assert sorted(bridge.deleted) == [0, 1]
    assert state.get("deleted") == 2


def test_icc_live_photo_pairs_as_one_asset(client, icc_reset):
    live_mov = _mp4_bytes()
    _install(
        icc_reset,
        FakeBridge(
            {"IMG_5001.HEIC": _jpeg("a"), "IMG_6002.JPG": _jpeg("b")},
            extras={"IMG_5001.HEIC": [("IMG_5001.MOV", live_mov)]},
        ),
    )

    job = client.post("/api/idevice/import", json={"serial": "ICC-UUID-1"}, headers=HEADERS).json()
    state = wait_job(client, job["job_id"])
    assert state["phase"] == "done", state
    assert state["counts"]["imported"] == 3

    items = client.get("/api/media").json()["items"]
    assert len(items) == 2, [i["name"] for i in items]
    photo = next(i for i in items if i["name"] == "IMG_5001.HEIC")
    assert photo["live_video_id"]

    meta = client.get(f"/api/media/{photo['id']}").json()
    assert meta["live_video_id"] == photo["live_video_id"]
    stream = client.get(f"/api/media/{photo['live_video_id']}/file")
    assert stream.status_code == 200 and stream.content == live_mov

    summary = client.get("/api/media/summary").json()
    assert sum(p["count"] for p in summary["periods"]) == 2


def test_icc_live_companion_purges_with_photo(client, icc_reset):
    _install(
        icc_reset,
        FakeBridge(
            {"IMG_7001.HEIC": _jpeg("a")},
            extras={"IMG_7001.HEIC": [("IMG_7001.MOV", _mp4_bytes())]},
        ),
    )
    job = client.post("/api/idevice/import", json={"serial": "ICC-UUID-1"}, headers=HEADERS).json()
    assert wait_job(client, job["job_id"])["phase"] == "done"
    photo = client.get("/api/media").json()["items"][0]
    companion_id = photo["live_video_id"]

    token = client.post("/api/vault/setup", json={"passkey": "livekey"}, headers=HEADERS).json()["token"]
    auth = {**HEADERS, "x-dam-vault": token}
    client.post(f"/api/media/{photo['id']}/trash", headers=HEADERS)
    assert client.delete(f"/api/trash/{photo['id']}", headers=auth).json()["ok"] is True
    assert client.get(f"/api/media/{companion_id}/file").status_code == 404


def test_icc_locked_device_reports_guidance(client, icc_reset):
    _install(icc_reset, FakeBridge({"IMG_9001.JPG": _jpeg("a")}, restricted=True))

    devices = client.get("/api/idevice/devices").json()["devices"]
    assert devices[0]["state"] == "locked-or-untrusted"

    contents = client.post("/api/idevice/contents", json={"serial": "ICC-UUID-1"}, headers=HEADERS)
    assert contents.status_code == 409 and "Trust This Computer" in contents.json()["detail"]

    job = client.post("/api/idevice/import", json={"serial": "ICC-UUID-1"}, headers=HEADERS).json()
    state = wait_job(client, job["job_id"])
    assert state["phase"] == "error"
    assert "Trust This Computer" in state["error"]


def test_icc_status_reports_reason_when_inactive(client, icc_reset):
    status = client.get("/api/idevice/status").json()
    assert status["native"]["active"] is False
    assert isinstance(status["native"]["reason"], str)
