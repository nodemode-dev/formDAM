import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

import pytest

from tests.support import BACKEND

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")

CHECK = (
    "import sys, desktop_entry; "
    "ok = all(s is not None for s in (sys.stdin, sys.stdout, sys.stderr)); "
    "open(sys.argv[1], 'w').write('streams ok' if ok else 'stream missing')"
)


def streams_after_import(tmp_path, closed):
    result = tmp_path / "result.txt"
    command = f"exec {shlex.quote(sys.executable)} -c {shlex.quote(CHECK)} {shlex.quote(str(result))} {closed}"
    done = subprocess.run(["sh", "-c", command], cwd=BACKEND)
    return done.returncode, result.read_text(encoding="utf-8") if result.exists() else ""


def test_the_entry_replaces_closed_output_streams(tmp_path):
    assert streams_after_import(tmp_path, ">&- 2>&-") == (0, "streams ok")


def test_the_entry_replaces_all_three_closed_streams(tmp_path):
    assert streams_after_import(tmp_path, "<&- >&- 2>&-") == (0, "streams ok")


def test_the_entry_keeps_the_pipes_its_parent_gave_it():
    check = "import sys, desktop_entry; print(sys.stdout is sys.__stdout__, sys.stdout.fileno(), sys.stderr is sys.__stderr__, sys.stderr.fileno())"
    done = subprocess.run([sys.executable, "-c", check], cwd=BACKEND, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert (done.returncode, done.stdout.strip()) == (0, "True 1 True 2")


def test_the_selfcheck_works_with_every_stream_closed(tmp_path):
    command = f"exec {shlex.quote(sys.executable)} desktop_entry.py --selfcheck <&- >&- 2>&-"
    assert subprocess.run(["sh", "-c", command], cwd=BACKEND, env=engine_env(tmp_path), timeout=120).returncode == 0


def engine_env(tmp_path, **extra):
    env = {key: value for key, value in os.environ.items() if not key.startswith(("FORMDAM_", "DAM_"))}
    env.update(HOME=str(tmp_path), FORMDAM_CONFIG=str(tmp_path / "config"), FORMDAM_LIBRARY=str(tmp_path / "library"), **extra)
    return env


def test_the_address_reaches_the_pipes_a_shell_reads(tmp_path):
    key = "k" * 64
    env = engine_env(tmp_path, FORMDAM_PORT="0", FORMDAM_SHELL_KEY=key, FORMDAM_SHELL_PID=str(os.getpid()))
    child = subprocess.Popen([sys.executable, "desktop_entry.py"], cwd=BACKEND, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = queue.Queue()

    def forward(stream):
        for raw in iter(stream.readline, b""):
            lines.put(raw.decode("utf-8", "replace").rstrip("\r\n"))

    for stream in (child.stdout, child.stderr):
        threading.Thread(target=forward, args=(stream,), daemon=True).start()
    seen, port = [], None
    try:
        until = time.monotonic() + 60
        while port is None and time.monotonic() < until:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                continue
            seen.append(line)
            found = re.search(r"http://127\.0\.0\.1:(\d+)", line)
            port = int(found.group(1)) if found else None
        assert port, seen
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=10) as answer:
            assert answer.status == 200
        assert not any(key in line for line in seen)
    finally:
        child.terminate()
        try:
            child.wait(10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(10)
