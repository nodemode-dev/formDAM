# Adapted from formlit backend/app/services/metadata.py (Apache-2.0, nodemode-ai); see LICENSES.md.
import json
import logging
import re
import struct
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any, Dict, Optional

from ..dedup.visual import ffprobe_path

logging.getLogger("exifread").setLevel(logging.ERROR)
APPLE_TAGS = {0x000B: "burst_id", 0x0011: "content_id", 0x0014: "capture_type", 0x002E: "camera_type"}
CAPTURE_TYPES = {1: "ProRAW", 2: "Portrait", 10: "Photo", 11: "Manual Focus", 12: "Scene"}
CAMERA_TYPES = {0: "Back Wide Angle", 1: "Back Normal", 6: "Front"}


def _num(v: Any) -> Optional[float]:
    try:
        if hasattr(v, "values"):
            v = v.values
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        if v is None:
            return None
        if hasattr(v, "num") and hasattr(v, "den"):
            return float(v.num) / float(v.den) if v.den else None
        return float(Fraction(str(v)))
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def _text(v: Any) -> str:
    s = str(getattr(v, "printable", v) or "").strip().strip("\x00")
    return re.sub(r"\s+", " ", s)


def _gps(tags: dict, key: str, ref: str) -> Optional[float]:
    v = tags.get(f"GPS {key}")
    if v is None:
        return None
    try:
        d, m, s = [float(x.num) / float(x.den) if x.den else 0.0 for x in v.values[:3]]
    except (AttributeError, ValueError, IndexError, TypeError):
        return None
    val = d + m / 60 + s / 3600
    if _text(tags.get(f"GPS {ref}", "")).upper() in ("S", "W"):
        val = -val
    return val


def _date_ts(s: str, offset: str = "") -> Optional[float]:
    s = s.strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
        if re.fullmatch(r"[+-]\d\d:\d\d", offset or ""):
            sign = 1 if offset[0] == "+" else -1
            minutes = int(offset[1:3]) * 60 + int(offset[4:6])
            return dt.replace(tzinfo=timezone.utc).timestamp() - sign * minutes * 60
        return dt.timestamp()
    return None


def _apple_makernote(raw: bytes) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not raw or not raw.startswith(b"Apple iOS\x00"):
        return out
    try:
        endian = ">" if raw[12:14] == b"MM" else "<"
        count = struct.unpack_from(endian + "H", raw, 14)[0]
        sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 8: 2, 9: 4, 10: 8, 16: 8}
        for i in range(min(count, 200)):
            base = 16 + i * 12
            tag, typ, n = struct.unpack_from(endian + "HHI", raw, base)
            if tag not in APPLE_TAGS:
                continue
            size = sizes.get(typ, 1) * n
            data = raw[base + 8: base + 12] if size <= 4 else raw[struct.unpack_from(endian + "I", raw, base + 8)[0]:][:size]
            if typ == 2:
                out[APPLE_TAGS[tag]] = data.split(b"\x00", 1)[0].decode("ascii", "replace").strip()
            elif typ in (3, 8):
                out[APPLE_TAGS[tag]] = struct.unpack_from(endian + "H", data)[0]
            elif typ in (4, 9):
                out[APPLE_TAGS[tag]] = struct.unpack_from(endian + "I", data)[0]
    except (struct.error, IndexError, ValueError):
        return out
    if isinstance(out.get("capture_type"), int):
        out["capture_type"] = CAPTURE_TYPES.get(out["capture_type"], str(out["capture_type"]))
    if isinstance(out.get("camera_type"), int):
        out["camera_type"] = CAMERA_TYPES.get(out["camera_type"], str(out["camera_type"]))
    return out


def _pillow_exif(path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        from PIL import Image

        with Image.open(path) as img:
            exif = img.getexif()
            sub = exif.get_ifd(0x8769)
            out["makernote"] = sub.get(0x927C) or b""
            if not exif:
                return out
            out["make"] = _text(exif.get(0x010F, ""))
            out["model"] = _text(exif.get(0x0110, ""))
            out["orientation"] = int(exif.get(0x0112) or 1)
            raw = sub.get(0x9003) or exif.get(0x0132)
            if raw:
                out["captured_ts"] = _date_ts(str(raw), str(sub.get(0x9011) or ""))
            out["aperture"] = _num(sub.get(0x829D))
            out["shutter"] = _num(sub.get(0x829A))
            out["iso"] = int(_num(sub.get(0x8827)) or 0) or None
            out["focal"] = _num(sub.get(0x920A))
            out["lens"] = _text(sub.get(0xA434, ""))
            gps = exif.get_ifd(0x8825)
            if gps and 2 in gps and 4 in gps:
                def dms(v):
                    return float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
                lat, lon = dms(gps[2]), dms(gps[4])
                if str(gps.get(1, "N")).upper().startswith("S"):
                    lat = -lat
                if str(gps.get(3, "E")).upper().startswith("W"):
                    lon = -lon
                out["lat"], out["lon"] = lat, lon
                if 6 in gps:
                    out["alt"] = float(gps[6]) * (-1 if gps.get(5) == 1 else 1)
    except Exception:
        return out
    return out


def read_image(path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    tags: Dict[str, Any] = {}
    try:
        import exifread

        with open(path, "rb") as handle:
            tags = exifread.process_file(handle, details=False, debug=False)
    except Exception:
        tags = {}
    pil = _pillow_exif(path)
    if tags:
        make = _text(tags.get("Image Make", ""))
        model = _text(tags.get("Image Model", ""))
        out["make"], out["model"] = make, model
        out["lens"] = _text(tags.get("EXIF LensModel", "") or tags.get("Image LensModel", "") or tags.get("EXIF LensSpecification", ""))
        out["focal"] = _num(tags.get("EXIF FocalLength") or tags.get("Image FocalLength"))
        out["focal35"] = _num(tags.get("EXIF FocalLengthIn35mmFilm"))
        out["aperture"] = _num(tags.get("EXIF FNumber") or tags.get("Image FNumber"))
        out["shutter"] = _num(tags.get("EXIF ExposureTime") or tags.get("Image ExposureTime"))
        iso = tags.get("EXIF ISOSpeedRatings") or tags.get("EXIF PhotographicSensitivity") or tags.get("Image ISOSpeedRatings")
        out["iso"] = int(_num(iso)) if _num(iso) else None
        fl = _num(tags.get("EXIF Flash"))
        out["flash"] = int(fl) & 1 if fl is not None else None
        o = _num(tags.get("Image Orientation"))
        out["orientation"] = int(o) if o else 1
        dt = _text(tags.get("EXIF DateTimeOriginal", "") or tags.get("Image DateTime", ""))
        if dt:
            out["captured_ts"] = _date_ts(dt, _text(tags.get("EXIF OffsetTimeOriginal", "")))
        out["lat"] = _gps(tags, "GPSLatitude", "GPSLatitudeRef")
        out["lon"] = _gps(tags, "GPSLongitude", "GPSLongitudeRef")
        alt = _num(tags.get("GPS GPSAltitude"))
        if alt is not None and _num(tags.get("GPS GPSAltitudeRef")) == 1:
            alt = -alt
        out["alt"] = alt
        out["software"] = _text(tags.get("Image Software", ""))
        out["artist"] = _text(tags.get("Image Artist", ""))
        out["copyright"] = _text(tags.get("Image Copyright", ""))
        full = {}
        for k, v in tags.items():
            if k in ("JPEGThumbnail", "TIFFThumbnail") or k.startswith(("MakerNote", "Thumbnail")):
                continue
            t = _text(v)
            if t and len(t) < 300:
                full[k] = t
        out["all"] = full
    for key, value in pil.items():
        if key != "makernote" and out.get(key) in (None, "") and value not in (None, ""):
            out[key] = value
    out.update(_apple_makernote(pil.get("makernote") or b""))
    out.update(_image_kinds(path))
    return {k: v for k, v in out.items() if v not in (None, "")}


def _image_kinds(path: str) -> Dict[str, Any]:
    found: Dict[str, Any] = {}
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("gif", "png", "webp", "apng"):
        try:
            from PIL import Image

            with Image.open(path) as img:
                if getattr(img, "n_frames", 1) > 1:
                    found["animated"] = True
        except Exception:
            pass
    if ext in ("heic", "heif"):
        try:
            import pillow_heif

            heif = pillow_heif.open_heif(path, convert_hdr_to_8bit=True)
            sizes = {tuple(im.size) for im in heif}
            if len(heif) >= 2 and len(sizes) == 1:
                found["spatial"] = True
        except Exception:
            pass
    return found


def _video_kinds(data: Dict[str, Any]) -> Dict[str, Any]:
    found: Dict[str, Any] = {}
    blobs = [((data.get("format") or {}).get("tags") or {})]
    for stream in data.get("streams", []):
        blobs.append(stream.get("tags") or {})
        for side in stream.get("side_data_list") or []:
            if "stereo" in str(side.get("side_data_type", "")).lower():
                found["spatial"] = True
    for tags in blobs:
        for key, value in tags.items():
            k, v = key.lower(), str(value).lower()
            if ("capture" in k and "mode" in k and "time" in v and "lapse" in v) or v in ("time-lapse", "timelapse"):
                found["timelapse"] = True
            if "cinematic" in k or ("handler" in k and "cinematic" in v):
                found["cinematic"] = True
            if "spatial" in k or ("stereo" in k and v not in ("0", "", "false")):
                found["spatial"] = True
    return found


ISO6709 = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?")


def read_video(path: str) -> Dict[str, Any]:
    probe = ffprobe_path()
    if not probe:
        return {}
    try:
        raw = subprocess.run(
            [probe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, timeout=20, check=True,
        ).stdout
        data = json.loads(raw or b"{}")
    except Exception:
        return {}
    out: Dict[str, Any] = {}
    tags = {k.lower(): v for k, v in ((data.get("format") or {}).get("tags") or {}).items()}
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
            try:
                out["fps"] = float(Fraction(rate)) if rate != "0/0" else None
            except (ValueError, ZeroDivisionError):
                pass
            for k, v in (stream.get("tags") or {}).items():
                tags.setdefault(k.lower(), v)
            break
    loc = tags.get("com.apple.quicktime.location.iso6709") or tags.get("location") or tags.get("location-eng")
    if loc:
        m = ISO6709.match(loc.strip())
        if m:
            out["lat"], out["lon"] = float(m.group(1)), float(m.group(2))
            if m.group(3):
                out["alt"] = float(m.group(3))
    out["make"] = tags.get("com.apple.quicktime.make") or tags.get("make") or ""
    out["model"] = tags.get("com.apple.quicktime.model") or tags.get("model") or ""
    out["content_id"] = tags.get("com.apple.quicktime.content.identifier") or ""
    out["software"] = tags.get("com.apple.quicktime.software") or tags.get("encoder") or ""
    out.update(_video_kinds(data))
    return {k: v for k, v in out.items() if v not in (None, "")}
