import re
import subprocess
import tomllib

from tests.support import REPO

STRIPPING = re.compile(r"strip\s*=\s*True|--strip\b")


def tracked(pattern):
    out = subprocess.run(["git", "ls-files", "--", pattern], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [REPO / line for line in out.splitlines() if line]


def stripped_profiles(data, trail=("profile",)):
    for key, value in data.items():
        if isinstance(value, dict):
            yield from stripped_profiles(value, trail + (key,))
        elif key == "strip" and value not in (False, "none"):
            yield ".".join(trail)


def test_the_tauri_manifest_was_found():
    assert (REPO / "src-tauri" / "Cargo.toml") in tracked("*Cargo.toml")


def test_no_cargo_release_profile_strips():
    found = []
    for path in tracked("*Cargo.toml"):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        found += [f"{path.relative_to(REPO).as_posix()} [{p}]" for p in stripped_profiles(data.get("profile", {}))]
    assert not found, found


def test_no_frozen_engine_build_strips():
    found = []
    for pattern in ("*.spec", "setup/*", "backend/boot_backend", "build_app*"):
        for path in tracked(pattern):
            text = path.read_text(encoding="utf-8", errors="replace")
            found += [f"{path.relative_to(REPO).as_posix()}: {m.group(0)}" for m in STRIPPING.finditer(text)]
    assert not found, found
