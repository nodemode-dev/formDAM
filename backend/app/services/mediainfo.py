import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional, Tuple

from PIL import ExifTags, Image, ImageOps

from ..dedup.visual import ffprobe_path

_EXIF_DTO = next((k for k, v in ExifTags.TAGS.items() if v == "DateTimeOriginal"), 36867)
_EXIF_DT = next((k for k, v in ExifTags.TAGS.items() if v == "DateTime"), 306)


def image_meta(path: str) -> Tuple[Optional[int], Optional[int], Optional[float]]:
    try:
        with Image.open(path) as img:
            transposed = ImageOps.exif_transpose(img)
            width, height = transposed.size
            exif_ts = None
            try:
                exif = img.getexif()
                raw = exif.get(_EXIF_DTO) or exif.get(_EXIF_DT)
                if raw:
                    exif_ts = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").timestamp()
            except Exception:
                exif_ts = None
            return width, height, exif_ts
    except Exception:
        return None, None, None


def video_meta(path: str) -> Tuple[Optional[int], Optional[int], Optional[float], Optional[float]]:
    probe = ffprobe_path()
    if not probe:
        return None, None, None, None
    try:
        raw = subprocess.run(
            [probe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, timeout=20, check=True,
        ).stdout
        data = json.loads(raw or b"{}")
    except Exception:
        return None, None, None, None
    width = height = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            break
    fmt = data.get("format", {})
    duration = None
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        duration = None
    created = None
    tag = (fmt.get("tags") or {}).get("creation_time")
    if tag:
        try:
            created = datetime.fromisoformat(str(tag).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        except ValueError:
            created = None
    return width, height, duration, created


def fs_created(path: str) -> Tuple[float, str]:
    st = os.stat(path)
    birth = getattr(st, "st_birthtime", None)
    if birth:
        return float(birth), "birthtime"
    return float(st.st_mtime), "mtime"
