import sys

import pytest

from app.services import filesvc
from tests.conftest import HEADERS, import_dir, pattern


@pytest.fixture
def launched(monkeypatch):
    calls = []
    monkeypatch.setattr(filesvc, "_run", lambda args: calls.append(args) or True)
    monkeypatch.setattr(filesvc, "editor_apps", lambda: ["Pixelmator Pro"])
    return calls


def test_a_listed_application_is_opened_on_macos(launched, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert filesvc.open_with("/photos/a.jpg", "Pixelmator Pro") is True
    assert launched == [["open", "-a", "Pixelmator Pro", "/photos/a.jpg"]]


def test_no_application_opens_the_default_one_on_macos(launched, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert filesvc.open_with("/photos/a.jpg") is True
    assert launched == [["open", "/photos/a.jpg"]]


@pytest.mark.parametrize("app", ["Unlisted", "/Applications/Other.app", "/bin/sh", "..\\..\\cmd.exe"])
@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_an_application_outside_the_list_is_refused(launched, monkeypatch, platform, app):
    monkeypatch.setattr(sys, "platform", platform)
    assert filesvc.open_with("/photos/a.jpg", app) is False
    assert launched == []


def test_the_open_route_refuses_an_application_the_window_never_offered(client, launched, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    pattern(64, 48).save(src / "a.jpg")
    import_dir(client, src)
    first = client.get("/api/media", headers=HEADERS).json()
    media_id = (first["items"] if isinstance(first, dict) else first)[0]["id"]
    refused = client.post(f"/api/media/{media_id}/open", json={"app": "/bin/sh"}, headers=HEADERS)
    assert refused.status_code == 200
    assert refused.json() == {"ok": False}
    edit = client.post(f"/api/media/{media_id}/edit-with", json={"app": "/bin/sh"}, headers=HEADERS)
    assert edit.status_code == 422
    assert launched == []
