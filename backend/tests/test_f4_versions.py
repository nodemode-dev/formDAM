import re

from tests.support import REPO, VERSION_SITES

VERSION = re.compile(r"^\d+\.\d+\.\d$")


def found():
    out = {}
    for i, (rel, pattern) in enumerate(VERSION_SITES):
        match = re.search(pattern, (REPO / rel).read_text(encoding="utf-8"), re.MULTILINE)
        out[f"{rel}#{i}"] = match.group(1) if match else None
    return out


def test_every_version_site_was_found():
    assert not [site for site, value in found().items() if value is None]


def test_every_version_site_agrees():
    assert len(set(found().values())) == 1, found()


def test_version_has_three_parts_and_a_one_digit_patch():
    assert VERSION.match(next(iter(found().values())))


def test_engine_reports_the_repository_version():
    from app.config import VERSION as engine_version

    assert engine_version == next(iter(found().values()))
