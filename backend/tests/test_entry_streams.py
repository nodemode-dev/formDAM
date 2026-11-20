import shlex
import shutil
import subprocess
import sys

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
