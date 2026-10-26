import pytest
from starlette.testclient import TestClient

from tests.conftest import HEADERS
from tests.support import OWN_ORIGIN, WINDOW_ORIGINS

FOREIGN_ORIGINS = [
    "http://evil.example",
    "https://evil.example",
    "http://localhost.evil.com",
    "http://127.0.0.1.evil.com",
    "http://localhost:3099",
    "http://127.0.0.1:3099",
    "http://localhost:5173.evil.com",
    "null",
    "file://",
]
FOREIGN_HOSTS = ["evil.example", "evil.example:8000", "localhost.evil.com:8000", "192.168.1.10:8000", "127.0.0.1.evil.com"]


@pytest.fixture
def anon(client):
    from app.main import app

    return TestClient(app, base_url=OWN_ORIGIN, client=("127.0.0.1", 51235))


def test_foreign_origins_are_not_in_the_apps_own_list():
    assert not set(FOREIGN_ORIGINS) & set(WINDOW_ORIGINS)


def test_window_origin_list_matches_the_engine(client):
    from app.security import WINDOW_ORIGINS as engine_list

    assert list(engine_list) == WINDOW_ORIGINS


@pytest.mark.parametrize("host", FOREIGN_HOSTS)
def test_foreign_host_is_refused(client, host):
    assert client.get("/api/health", headers={"host": host}).status_code == 403


@pytest.mark.parametrize("origin", FOREIGN_ORIGINS)
def test_foreign_origin_is_refused(client, origin):
    assert client.get("/api/health", headers={"origin": origin}).status_code == 403


@pytest.mark.parametrize("origin", FOREIGN_ORIGINS)
def test_foreign_origin_cannot_post_session(anon, origin):
    assert anon.post("/api/session", headers={"origin": origin, **HEADERS}).status_code == 403


@pytest.mark.parametrize("path", ["/api/health", "/api/session", "/api/missing-route"])
def test_foreign_origin_is_refused_on_every_kind_of_path(client, path):
    assert client.get(path, headers={"origin": "http://evil.example"}).status_code == 403


def test_cross_site_request_without_origin_is_refused(client):
    assert client.get("/api/health", headers={"sec-fetch-site": "cross-site"}).status_code == 403


@pytest.mark.parametrize("value", ["CROSS-SITE", " cross-site "])
def test_cross_site_marker_is_read_loosely(client, value):
    assert client.get("/api/health", headers={"sec-fetch-site": value}).status_code == 403


@pytest.mark.parametrize("origin", [OWN_ORIGIN, *WINDOW_ORIGINS])
def test_allowed_origin_passes(client, origin):
    assert client.get("/api/health", headers={"origin": origin}).status_code == 200


def test_own_origin_must_match_the_host_it_was_sent_to(client):
    assert client.get("/api/health", headers={"host": "127.0.0.1:8000", "origin": "http://127.0.0.1:8001"}).status_code == 403


@pytest.mark.parametrize("host", ["localhost:8000", "[::1]:8000", "127.0.0.1:8000"])
def test_own_origin_under_a_loopback_host_passes(client, host):
    assert client.get("/api/health", headers={"host": host, "origin": f"http://{host}"}).status_code == 200


@pytest.mark.parametrize("site", ["same-origin", "same-site", "none"])
def test_browser_request_without_origin_passes_unless_cross_site(client, site):
    assert client.get("/api/health", headers={"sec-fetch-site": site}).status_code == 200


def test_non_loopback_peer_is_refused(client):
    from app.main import app

    with TestClient(app, base_url=OWN_ORIGIN, client=("10.0.0.9", 4444)) as remote:
        assert remote.get("/api/health").status_code == 403


def test_websocket_surface_is_absent(client):
    from app.main import app

    assert not [r for r in app.routes if type(r).__name__ == "WebSocketRoute"]


def test_session_needs_the_launch_key(anon):
    assert anon.get("/api/session").json() == {"window": False}
    assert anon.post("/api/session", headers=HEADERS).status_code == 403
    assert anon.post("/api/session", headers={"x-dam-shell": "0" * 64, **HEADERS}).status_code == 403
    assert anon.get("/api/session").json() == {"window": False}


def test_launch_key_opens_a_window_session(anon):
    from app.security import LAUNCH_KEY

    opened = anon.post("/api/session", headers={"x-dam-shell": LAUNCH_KEY, **HEADERS})
    assert opened.status_code == 200 and opened.json() == {"window": True}
    cookie = opened.headers["set-cookie"].lower()
    assert "dam_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert anon.get("/api/session").json() == {"window": True}
    assert anon.get("/api/summary").status_code == 200


@pytest.mark.parametrize("path", ["/api/summary", "/api/media", "/api/library"])
def test_api_without_a_window_session_or_token_is_refused(anon, path):
    assert anon.get(path).status_code == 403


def test_a_forged_session_cookie_is_refused(anon):
    anon.cookies.set("dam_session", "f" * 64)
    assert anon.get("/api/summary").status_code == 403


def test_launch_key_header_alone_opens_the_api(anon):
    from app.security import LAUNCH_KEY

    assert anon.get("/api/summary", headers={"x-dam-shell": LAUNCH_KEY}).status_code == 200


def test_mutating_call_needs_the_local_header(client):
    assert client.post("/api/import", json={"path": "/tmp"}).status_code == 403


def test_automation_is_off_by_default_and_a_token_is_refused_while_off(anon):
    assert anon.get("/api/summary", headers={"x-dam-automation": "dam_guess"}).status_code == 403


def test_automation_cannot_be_turned_on_without_the_window(anon):
    assert anon.put("/api/system/automation", json={"enabled": True}, headers=HEADERS).status_code == 403


def test_automation_token_works_only_while_on(client, anon):
    on = client.put("/api/system/automation", json={"enabled": True}, headers=HEADERS)
    assert on.status_code == 200
    token = on.json()["token"]
    from app.security import forget_automation

    forget_automation()
    assert anon.get("/api/summary", headers={"x-dam-automation": token}).status_code == 200
    assert anon.get("/api/summary", headers={"x-dam-automation": token + "x"}).status_code == 403
    client.put("/api/system/automation", json={"enabled": False}, headers=HEADERS)
    forget_automation()
    assert anon.get("/api/summary", headers={"x-dam-automation": token}).status_code == 403
