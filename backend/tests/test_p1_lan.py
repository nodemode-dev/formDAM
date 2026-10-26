import time

import pytest
from starlette.testclient import TestClient

from tests.conftest import HEADERS

PEER = ("192.168.1.20", 50000)


@pytest.fixture
def lan(client):
    from app import familyserver

    assert not familyserver.running()
    yield TestClient(familyserver.app, base_url="http://192.168.1.10:8792", client=PEER)
    familyserver.stop()


def enable(client):
    key = client.post("/api/family/key", json={}, headers=HEADERS).json()["key"]
    assert client.put("/api/family", json={"enabled": True, "port": free_port()}, headers=HEADERS).status_code == 200
    return key


def free_port():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def signed(path, device="a" * 32, nonce="b" * 32, ts=None, sig=None):
    from app.services import familynet

    ts = str(time.time() if ts is None else ts)
    return {"x-fam-device": device, "x-fam-ts": ts, "x-fam-nonce": nonce,
            "x-fam-sig": sig if sig is not None else familynet.sign("GET", path, ts, nonce, device)}


def test_lan_server_is_off_by_default(client):
    from app import familyserver
    from app.services import familynet

    state = client.get("/api/family").json()
    assert state["enabled"] is False
    assert familynet.settings()["enabled"] is False
    assert familyserver.running() is False
    assert familyserver.sync_state() is False and familyserver.running() is False


def test_enabling_without_a_key_is_refused(client):
    assert client.put("/api/family", json={"enabled": True}, headers=HEADERS).status_code == 400
    assert client.get("/api/family").json()["enabled"] is False


def test_requests_are_refused_while_the_server_is_off(lan):
    assert lan.get("/f/hello").status_code == 403


def test_unpaired_device_is_refused_when_on(client, lan):
    enable(client)
    assert lan.get("/f/hello").status_code == 401
    assert lan.get("/f/journal").status_code == 401


def test_wrong_signature_is_refused(client, lan):
    enable(client)
    assert lan.get("/f/hello", headers=signed("/f/hello", sig="0" * 64)).status_code == 401
    assert lan.get("/f/hello", headers=signed("/f/journal")).status_code == 401


def test_stale_timestamp_is_refused(client, lan):
    enable(client)
    assert lan.get("/f/hello", headers=signed("/f/hello", ts=time.time() - 3600)).status_code == 401


def test_paired_device_is_served_once_and_a_replay_is_refused(client, lan):
    enable(client)
    headers = signed("/f/hello")
    assert lan.get("/f/hello", headers=headers).status_code == 200
    assert lan.get("/f/hello", headers=headers).status_code == 401


def test_public_address_is_refused_even_with_a_valid_signature(client):
    from app import familyserver

    enable(client)
    outside = TestClient(familyserver.app, base_url="http://192.168.1.10:8792", client=("8.8.8.8", 50000))
    assert outside.get("/f/hello", headers=signed("/f/hello", nonce="c" * 32)).status_code == 403
    familyserver.stop()


def test_server_only_answers_get_under_f(client, lan):
    enable(client)
    assert lan.post("/f/hello", headers=signed("/f/hello", nonce="d" * 32)).status_code == 404
    assert lan.get("/api/health", headers=signed("/api/health", nonce="e" * 32)).status_code == 404


def test_turning_it_off_stops_the_server(client, lan):
    from app import familyserver

    enable(client)
    assert familyserver.running()
    assert client.put("/api/family", json={"enabled": False}, headers=HEADERS).status_code == 200
    assert familyserver.running() is False
