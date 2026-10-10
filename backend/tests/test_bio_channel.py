import threading
import time

from tests.conftest import HEADERS


def _drain_nonce(client):
    for _ in range(200):
        from app.routers.trash import PENDING

        if PENDING:
            return next(iter(PENDING))
        time.sleep(0.01)
    raise AssertionError("no pending nonce appeared")


def test_shell_hello_drives_keychain_status(client):
    assert client.get("/api/vault/keychain/status").json() == {"available": False, "stored": False}
    client.post("/api/internal/shell/hello", json={"bio": True, "stored": False}, headers=HEADERS)
    assert client.get("/api/vault/keychain/status").json() == {"available": True, "stored": False}


def test_bio_unlock_roundtrip(client):
    client.post("/api/vault/setup", json={"passkey": "hunter22"}, headers=HEADERS)
    client.post("/api/internal/shell/hello", json={"bio": True, "stored": True}, headers=HEADERS)

    result = {}

    def unlock():
        result["res"] = client.post("/api/vault/bio/unlock", headers=HEADERS)

    worker = threading.Thread(target=unlock)
    worker.start()
    nonce = _drain_nonce(client)
    client.post("/api/internal/bio/result", json={"nonce": nonce, "ok": True, "passkey": "hunter22"}, headers=HEADERS)
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert "token" in result["res"].json()


def test_keychain_enable_roundtrip_and_bad_passkey(client):
    client.post("/api/vault/setup", json={"passkey": "hunter22"}, headers=HEADERS)
    client.post("/api/internal/shell/hello", json={"bio": True, "stored": False}, headers=HEADERS)

    assert client.post("/api/vault/keychain/enable", json={"passkey": "wrong-pass"}, headers=HEADERS).status_code == 401

    result = {}

    def enable():
        result["res"] = client.post("/api/vault/keychain/enable", json={"passkey": "hunter22"}, headers=HEADERS)

    worker = threading.Thread(target=enable)
    worker.start()
    nonce = _drain_nonce(client)
    from app.routers.trash import PENDING

    assert PENDING[nonce]["passkey"] == "hunter22"
    client.post("/api/internal/bio/result", json={"nonce": nonce, "ok": True, "stored": True}, headers=HEADERS)
    worker.join(timeout=5)
    assert result["res"].json() == {"ok": True}
    assert client.get("/api/vault/keychain/status").json()["stored"] is True


def test_window_control_clamps(client):
    res = client.post("/api/system/window", json={"blur": 999, "clear": True}, headers=HEADERS).json()
    assert res == {"blur": 64, "clear": True}
    low = client.post("/api/system/window", json={"blur": -3}, headers=HEADERS).json()
    assert low == {"blur": 0}
    shown = client.post("/api/system/window", json={"ready": True}, headers=HEADERS).json()
    assert shown == {"ready": True}
