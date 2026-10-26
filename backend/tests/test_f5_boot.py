import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from tests.support import BACKEND, REPO


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_json(url):
    with urllib.request.urlopen(url, timeout=2) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    root = tmp_path_factory.mktemp("boot")
    home = root / "home"
    home.mkdir()
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FORMDAM_", "DAM_", "DAMP_"))}
    env.update(DAM_LIBRARY=str(root / "library"), HOME=str(home), USERPROFILE=str(home), FORMDAM_SHELL_KEY="b" * 64)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 90
    ready = False
    while time.monotonic() < deadline and proc.poll() is None and not ready:
        try:
            ready = get_json(base + "/api/health")[0] == 200
        except OSError:
            time.sleep(0.25)
    if not ready:
        proc.kill()
        raise RuntimeError(proc.communicate(timeout=5)[0].decode("utf-8", "replace")[-4000:])
    yield {"base": base, "root": root, "home": home, "proc": proc}
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_engine_boots_on_a_free_port_with_an_empty_library(engine):
    assert get_json(engine["base"] + "/api/health")[0] == 200
    assert engine["proc"].poll() is None


def test_engine_reports_the_repository_version(engine):
    package = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    body = get_json(engine["base"] + "/api/health")[1]
    assert body["ok"] is True and body["version"] == package["version"]


def test_engine_keeps_its_data_in_the_library_it_was_given(engine):
    assert (engine["root"] / "library" / "dam.db").is_file()
    assert body_library(engine) == str(engine["root"] / "library")
    assert not [p for p in engine["home"].rglob("*") if "dam" in p.name.lower()]


def body_library(engine):
    return get_json(engine["base"] + "/api/health")[1]["library"]


def test_window_session_opens_with_the_launch_key_over_http(engine):
    request = urllib.request.Request(engine["base"] + "/api/session", data=b"", method="POST",
                                     headers={"x-dam-shell": "b" * 64, "x-dam-local": "1"})
    with urllib.request.urlopen(request, timeout=3) as r:
        assert r.status == 200 and "dam_session=" in r.headers["set-cookie"]
