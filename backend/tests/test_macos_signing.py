import os
import shutil
import subprocess

import pytest

from tests.support import REPO

HELPER = REPO / "setup" / "macos_identity"
DEVELOPER_ID = "Developer ID Application: Example (TEAM123456)"

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")


def resolve(tmp_path, identity):
    stub = tmp_path / "bin"
    stub.mkdir()
    marker = tmp_path / "keychain-searched"
    (stub / "security").write_text(f'#!/bin/sh\n: > "{marker}"\necho \'  1) ABCDEF "{DEVELOPER_ID}"\'\n')
    (stub / "security").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "APPLE_SIGNING_IDENTITY"}
    env["PATH"] = f"{stub}{os.pathsep}{env.get('PATH', '')}"
    if identity is not None:
        env["APPLE_SIGNING_IDENTITY"] = identity
    script = f'. "{HELPER}"; macos_identity; printf "%s|%s" "$IDENTITY" "$MACOS_ADHOC"'
    out = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, check=True).stdout
    return out, marker.exists()


def test_a_dash_means_ad_hoc_and_the_keychain_is_never_searched(tmp_path):
    assert resolve(tmp_path, "-") == ("|1", False)


def test_no_identity_takes_the_developer_id_from_the_keychain(tmp_path):
    assert resolve(tmp_path, None) == (f"{DEVELOPER_ID}|0", True)


def test_a_named_identity_is_used_as_given(tmp_path):
    assert resolve(tmp_path, DEVELOPER_ID) == (f"{DEVELOPER_ID}|0", False)


def test_both_macos_scripts_resolve_the_identity_through_the_helper():
    for name in ("build_macos_app", "package_dmg"):
        text = (REPO / "setup" / name).read_text(encoding="utf-8")
        assert "macos_identity" in text and "find-identity" not in text, name
