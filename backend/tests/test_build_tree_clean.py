import re
import subprocess

from tests.support import REPO

ICON_CALL = re.compile(r"@tauri-apps/cli@\S+\s+icon\s+(.*)")
GENERATED = ["src-tauri/Info.plist", "src-tauri/icons/android/x.png", "src-tauri/icons/ios/x.png", "src-tauri/icons/iconassets/Assets.car",
             "src-tauri/icons/icon.ico", "src-tauri/icons/icon.icns", "src-tauri/icons/32x32.png"]


def tracked(path):
    return subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=REPO, capture_output=True).returncode == 0


def test_every_icon_generation_writes_outside_the_tracked_icons():
    calls = []
    for script in sorted((REPO / "setup").iterdir()):
        for line in script.read_text(encoding="utf-8", errors="replace").splitlines():
            match = ICON_CALL.search(line)
            if match:
                calls.append((script.name, match.group(1)))
    assert calls
    assert [c for c in calls if not re.search(r"(^|\s)-o\s", c[1])] == []


def test_generated_build_outputs_are_ignored():
    out = subprocess.run(["git", "check-ignore", "--no-index", *GENERATED], cwd=REPO, capture_output=True, text=True).stdout.split()
    assert sorted(out) == sorted(GENERATED)


def test_the_source_icon_stays_tracked():
    assert tracked("src-tauri/icons/icon.png")
    assert tracked("src-tauri/icons/source/icon.icns")
