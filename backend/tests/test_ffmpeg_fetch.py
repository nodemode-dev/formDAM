import hashlib
import io
import tarfile
import urllib.error

import pytest

from app import ffmpeg_fetch

GOOD = {"ffmpeg": b"engine-bytes", "ffprobe": b"probe-bytes"}


def archive(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as bundle:
        for name, data in files.items():
            info = tarfile.TarInfo(f"pack/{name}")
            info.size = len(data)
            info.mode = 0o755
            bundle.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def world(tmp_path, monkeypatch):
    triple = ffmpeg_fetch.host_triple()
    names = {f"{program}-{triple}": data for program, data in GOOD.items()}
    pins = tuple((name, hashlib.sha256(data).hexdigest()) for name, data in names.items())
    monkeypatch.setitem(ffmpeg_fetch.FILES, triple, pins)
    monkeypatch.setattr(ffmpeg_fetch, "folder", lambda: tmp_path / "shared" / "ffmpeg")
    monkeypatch.delenv("FORMCUT_FFMPEG_RELEASE", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    served = {}
    asked = []

    def download(url, target):
        asked.append(url)
        if url not in served:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        target.write_bytes(served[url])

    monkeypatch.setattr(ffmpeg_fetch, "_download", download)
    return {"names": names, "served": served, "asked": asked, "where": tmp_path / "shared" / "ffmpeg"}


def tampered(world):
    return archive({name: data + b"-changed" for name, data in world["names"].items()})


def test_the_new_address_is_tried_first_and_the_old_one_second():
    urls = ffmpeg_fetch.sources()
    assert len(urls) == 2
    assert "/nodemode-dev/formai-binaries/releases/download/ffmpeg-" in urls[0]
    assert "/nodemode-dev/formcut-binaries/releases/download/ffmpeg-" in urls[1]
    assert urls[0].split("/download/")[1] == urls[1].split("/download/")[1]
    assert urls[0].endswith(f"ffmpeg-lgpl-{ffmpeg_fetch.RELEASE}-{ffmpeg_fetch.host_triple()}.tar.gz")


def test_the_override_is_the_only_source(monkeypatch):
    monkeypatch.setenv("FORMCUT_FFMPEG_RELEASE", "http://mirror.invalid/pack/")
    assert ffmpeg_fetch.sources() == [
        f"http://mirror.invalid/pack/ffmpeg-lgpl-{ffmpeg_fetch.RELEASE}-{ffmpeg_fetch.host_triple()}.tar.gz"
    ]


def test_the_first_address_answering_is_the_only_one_asked(world):
    first, second = ffmpeg_fetch.sources()
    world["served"][first] = archive(world["names"])
    world["served"][second] = archive(world["names"])
    assert ffmpeg_fetch.fetch() == world["where"]
    assert world["asked"] == [first]


def test_a_missing_new_address_falls_back_to_the_old_one(world):
    first, second = ffmpeg_fetch.sources()
    world["served"][second] = archive(world["names"])
    assert ffmpeg_fetch.fetch() == world["where"]
    assert world["asked"] == [first, second]
    assert (world["where"] / f"ffmpeg-{ffmpeg_fetch.host_triple()}").read_bytes() == GOOD["ffmpeg"]


def test_a_wrong_hash_from_the_first_address_moves_on_to_the_second(world):
    first, second = ffmpeg_fetch.sources()
    world["served"][first] = tampered(world)
    world["served"][second] = archive(world["names"])
    assert ffmpeg_fetch.fetch() == world["where"]
    assert world["asked"] == [first, second]
    assert (world["where"] / f"ffprobe-{ffmpeg_fetch.host_triple()}").read_bytes() == GOOD["ffprobe"]


def test_a_wrong_hash_from_every_address_installs_nothing(world):
    for url in ffmpeg_fetch.sources():
        world["served"][url] = tampered(world)
    with pytest.raises(ValueError, match="does not match the record"):
        ffmpeg_fetch.fetch()
    assert not world["where"].exists()


def test_both_addresses_failing_raises_and_installs_nothing(world):
    with pytest.raises(ValueError, match="404"):
        ffmpeg_fetch.fetch()
    assert len(world["asked"]) == 2
    assert not world["where"].exists()


def test_with_the_override_set_the_built_in_addresses_are_never_asked(world, monkeypatch):
    monkeypatch.setenv("FORMCUT_FFMPEG_RELEASE", "http://mirror.invalid/pack")
    for url in ffmpeg_fetch.SOURCES:
        world["served"][url] = archive(world["names"])
    with pytest.raises(ValueError):
        ffmpeg_fetch.fetch()
    assert world["asked"] == ffmpeg_fetch.sources()
    assert not world["where"].exists()


def test_the_override_still_installs_when_its_files_match(world, monkeypatch):
    monkeypatch.setenv("FORMCUT_FFMPEG_RELEASE", "http://mirror.invalid/pack")
    (url,) = ffmpeg_fetch.sources()
    world["served"][url] = archive(world["names"])
    assert ffmpeg_fetch.fetch() == world["where"]
    assert world["asked"] == [url]
