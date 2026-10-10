import os
import subprocess
from typing import Optional

from PIL import Image

from ..config import cache_dir
from ..dedup.visual import ffmpeg_path
from . import libraryfs

SIZES = (192, 384, 768)


def _bucket(requested: int) -> int:
    for size in SIZES:
        if requested <= size:
            return size
    return SIZES[-1]


THUMB_VER = 4


def thumb_folder() -> str:
    folder = os.path.join(cache_dir(), "thumbs")
    os.makedirs(folder, exist_ok=True)
    return folder


def thumb_path(media_id: int, size: int) -> str:
    return os.path.join(thumb_folder(), f"{media_id}_{size}_v{THUMB_VER}.webp")


def legacy_thumb_path(media_id: int, size: int) -> str:
    return os.path.join(thumb_folder(), f"{media_id}_{size}_v3.jpg")


def convert_legacy(src: str, dst: str) -> bool:
    """Re-encode one legacy JPEG thumb to WebP; atomic, best-effort."""
    tmp = dst + ".tmp"
    try:
        with Image.open(src) as img:
            img.convert("RGB").save(tmp, "WEBP", quality=80, method=4)
        os.replace(tmp, dst)
        try:
            os.unlink(src)
        except OSError:
            pass
        return True
    except Exception:
        if os.path.isfile(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False


def ensure_thumb(media_id: int, rel_path: str, kind: str, requested: int) -> Optional[str]:
    size = _bucket(requested)
    out = thumb_path(media_id, size)
    if os.path.isfile(out):
        return out
    legacy = legacy_thumb_path(media_id, size)
    if os.path.isfile(legacy) and convert_legacy(legacy, out):
        return out
    src = libraryfs.abs_path(rel_path)
    if not os.path.isfile(src):
        return None
    if kind == "image":
        try:
            from . import decode, editsvc

            frame = editsvc.render_still(media_id, src, size)
            if frame is None:
                frame = decode.open_image(src, rel_path, max_long=size)
            if frame is None:
                return None
            frame.convert("RGB").save(out, "WEBP", quality=80, method=4)
            return out
        except Exception:
            return None
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        grab = out + ".frame.jpg"
        for seek in ("0", "0.5"):
            try:
                subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", seek, "-i", src,
                     "-frames:v", "1", "-vf", f"scale={size}:-2", "-y", grab],
                    capture_output=True, timeout=30, check=True,
                )
                if os.path.isfile(grab) and os.path.getsize(grab) > 0:
                    with Image.open(grab) as img:
                        img.convert("RGB").save(out, "WEBP", quality=80, method=4)
                    os.unlink(grab)
                    for stale in (f"{media_id}_{size}_ph.webp", f"{media_id}_{size}_ph.jpg"):
                        stale_path = os.path.join(os.path.dirname(out), stale)
                        if os.path.isfile(stale_path):
                            os.unlink(stale_path)
                    return out
            except Exception:
                pass
            for leftover in (grab, out):
                if os.path.isfile(leftover):
                    try:
                        os.unlink(leftover)
                    except OSError:
                        pass
    ph = os.path.join(os.path.dirname(out), f"{media_id}_{size}_ph.webp")
    if not os.path.isfile(ph):
        _placeholder_poster(ph, size)
    return ph if os.path.isfile(ph) else None


def _placeholder_poster(target: str, size: int) -> None:
    height = max(2, int(size * 9 / 16))
    img = Image.new("RGB", (size, height), (24, 22, 18))
    img.save(target, "WEBP", quality=80, method=4)
