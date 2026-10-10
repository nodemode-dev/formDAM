import math
import os
import threading
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


DHASH_BITS = 128
PHASH_BITS = 64
FLAT_RANGE = 10
FLOOR_SIMILARITY = 58
DEFAULT_SIMILARITY = 94
COLOR_SCALE = 64
STRUCT_WEIGHT = 0.42
SPECTRUM_WEIGHT = 0.38
COLOR_WEIGHT = 0.20
VIDEO_SAMPLE_POINTS = (0.12, 0.30, 0.50, 0.70, 0.88)
VIDEO_FRAME_EDGE = 64
VIDEO_DURATION_SLACK_S = 2.0
VIDEO_DURATION_SLACK_FRAC = 0.06
_MEMBER_PROBE_LIMIT = 3
PHASH_CONFIDENT_FLOOR = 2.0
PHASH_FULL_WEIGHT_AT = 24

FrameSig = Tuple[int, int, int, bytes]


@dataclass
class VisualSig:
    dhash: int
    phash: int
    pmask: int
    color: bytes
    width: int
    height: int
    media: str = "image"
    flat: bool = False
    frames: Tuple[FrameSig, ...] = ()
    duration: float = 0.0


_DCT_LOCK = threading.Lock()
_DCT_ROWS: Optional[List[List[float]]] = None


def _dct_rows() -> List[List[float]]:
    global _DCT_ROWS
    with _DCT_LOCK:
        if _DCT_ROWS is None:
            n = 32
            rows: List[List[float]] = []
            for u in range(8):
                scale = math.sqrt(1.0 / n) if u == 0 else math.sqrt(2.0 / n)
                rows.append([scale * math.cos((2 * x + 1) * u * math.pi / (2 * n)) for x in range(n)])
            _DCT_ROWS = rows
        return _DCT_ROWS


def _phash_from_gray32(pixels: Sequence[int]) -> Tuple[int, int]:
    rows = _dct_rows()
    grid = [pixels[y * 32 : (y + 1) * 32] for y in range(32)]
    partial = [[sum(rows[u][x] * grid[y][x] for x in range(32)) for y in range(32)] for u in range(8)]
    coeffs: List[float] = []
    for u in range(8):
        line = partial[u]
        for v in range(8):
            row = rows[v]
            coeffs.append(sum(row[y] * line[y] for y in range(32)))
    tail = sorted(coeffs[1:])
    median = (tail[30] + tail[31]) / 2.0
    deviations = sorted(abs(value - median) for value in coeffs[1:])
    mad = (deviations[30] + deviations[31]) / 2.0
    tau = max(PHASH_CONFIDENT_FLOOR, mad)
    bits = 0
    mask = 0
    for value in coeffs:
        bits = (bits << 1) | (1 if value > median else 0)
        mask = (mask << 1) | (1 if abs(value - median) >= tau else 0)
    return bits, mask


def _flat(image) -> List[int]:
    getter = getattr(image, "get_flattened_data", None)
    raw = getter() if getter is not None else image.getdata()
    values: List[int] = []
    for pixel in raw:
        if isinstance(pixel, tuple):
            values.extend(pixel)
        else:
            values.append(pixel)
    return values


def _dhash_from_gray(gray) -> Tuple[int, bool]:
    from PIL import Image

    horizontal = _flat(gray.resize((9, 8), Image.Resampling.BILINEAR))
    vertical = _flat(gray.resize((8, 9), Image.Resampling.BILINEAR))
    flat = max(horizontal) - min(horizontal) < FLAT_RANGE
    h_bits = 0
    for row in range(8):
        for col in range(8):
            h_bits = (h_bits << 1) | (1 if horizontal[row * 9 + col] > horizontal[row * 9 + col + 1] else 0)
    v_bits = 0
    for row in range(8):
        for col in range(8):
            v_bits = (v_bits << 1) | (1 if vertical[row * 8 + col] > vertical[(row + 1) * 8 + col] else 0)
    return (h_bits << 64) | v_bits, flat


def _frame_sig(image) -> Tuple[FrameSig, bool]:
    from PIL import Image

    gray = image.convert("L")
    dhash, flat = _dhash_from_gray(gray)
    phash, pmask = _phash_from_gray32(_flat(gray.resize((32, 32), Image.Resampling.BILINEAR)))
    color = bytes(_flat(image.convert("RGB").resize((4, 4), Image.Resampling.BILINEAR)))
    return (dhash, phash, pmask, color), flat


def image_signature(path: str) -> Optional[VisualSig]:
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as opened:
            width, height = opened.size
            try:
                opened.draft(None, (128, 128))
            except Exception:
                pass
            image = ImageOps.exif_transpose(opened)
            (dhash, phash, pmask, color), flat = _frame_sig(image)
    except Exception:
        return None
    return VisualSig(
        dhash=dhash, phash=phash, pmask=pmask, color=color,
        width=width, height=height, media="image", flat=flat,
    )


BREW_BINS = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin")


def _find_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for base in BREW_BINS:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


def ffmpeg_path() -> str:
    return _find_tool("ffmpeg")


def ffprobe_path() -> str:
    return _find_tool("ffprobe")


def _probe_video(path: str) -> Optional[Tuple[float, int, int]]:
    binary = ffprobe_path()
    if not binary:
        return None
    command = [
        binary, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "csv=p=0:nk=1", path,
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    width = height = 0
    duration = 0.0
    for token in proc.stdout.replace("\n", ",").split(","):
        token = token.strip()
        if not token or token == "N/A":
            continue
        if "." in token and duration == 0.0:
            try:
                duration = float(token)
                continue
            except ValueError:
                pass
        if token.isdigit():
            if width == 0:
                width = int(token)
            elif height == 0:
                height = int(token)
    if width <= 0 or height <= 0:
        return None
    return duration, width, height


def _grab_frame(path: str, timestamp: float):
    from PIL import Image

    binary = ffmpeg_path()
    if not binary:
        return None
    command = [
        binary, "-hide_banner", "-loglevel", "error", "-noaccurate_seek",
        "-ss", f"{max(0.0, timestamp):.2f}", "-i", path, "-frames:v", "1",
        "-vf", f"scale={VIDEO_FRAME_EDGE}:{VIDEO_FRAME_EDGE}:flags=area",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    try:
        proc = subprocess.run(command, capture_output=True, timeout=60)
    except Exception:
        return None
    expected = VIDEO_FRAME_EDGE * VIDEO_FRAME_EDGE * 3
    if proc.returncode != 0 or len(proc.stdout) < expected:
        return None
    return Image.frombytes("RGB", (VIDEO_FRAME_EDGE, VIDEO_FRAME_EDGE), proc.stdout[:expected])


def video_signature(path: str) -> Optional[VisualSig]:
    probed = _probe_video(path)
    if probed is None:
        return None
    duration, width, height = probed
    if duration and duration > 1.0:
        timestamps = [duration * point for point in VIDEO_SAMPLE_POINTS]
    else:
        timestamps = [0.0]
    frames: List[FrameSig] = []
    all_flat = True
    for timestamp in timestamps:
        frame = _grab_frame(path, timestamp)
        if frame is None and timestamp > 0:
            frame = _grab_frame(path, 0.0)
        if frame is None:
            continue
        sig, flat = _frame_sig(frame)
        frames.append(sig)
        all_flat = all_flat and flat
    if not frames:
        return None
    first = frames[0]
    return VisualSig(
        dhash=first[0], phash=first[1], pmask=first[2], color=first[3],
        width=width, height=height, media="video", flat=all_flat,
        frames=tuple(frames), duration=duration or 0.0,
    )


def _norm_component(raw_fraction: float) -> float:
    return max(0.0, (raw_fraction - 0.5) / 0.5) * 100.0


def _frame_similarity(a: FrameSig, b: FrameSig) -> float:
    struct = _norm_component(1.0 - (a[0] ^ b[0]).bit_count() / DHASH_BITS)
    confident = a[2] & b[2]
    considered = confident.bit_count()
    if considered:
        disagree = ((a[1] ^ b[1]) & confident).bit_count()
        spectrum = _norm_component(1.0 - disagree / considered)
    else:
        spectrum = 0.0
    mad = sum(abs(x - y) for x, y in zip(a[3], b[3])) / len(a[3])
    color = max(0.0, 100.0 - mad * 100.0 / COLOR_SCALE)
    confidence = min(1.0, considered / PHASH_FULL_WEIGHT_AT)
    spectrum_weight = SPECTRUM_WEIGHT * confidence
    spare = SPECTRUM_WEIGHT - spectrum_weight
    base = STRUCT_WEIGHT + COLOR_WEIGHT
    struct_weight = STRUCT_WEIGHT + spare * (STRUCT_WEIGHT / base)
    color_weight = COLOR_WEIGHT + spare * (COLOR_WEIGHT / base)
    return struct_weight * struct + spectrum_weight * spectrum + color_weight * color


def similarity(a: VisualSig, b: VisualSig) -> int:
    if a.media != b.media:
        return 0
    if a.media == "video":
        gap = abs(a.duration - b.duration)
        slack = max(VIDEO_DURATION_SLACK_S, VIDEO_DURATION_SLACK_FRAC * max(a.duration, b.duration))
        if a.duration and b.duration and gap > slack:
            return 0
        count = min(len(a.frames), len(b.frames))
        if count == 0:
            return 0
        total = sum(_frame_similarity(a.frames[i], b.frames[i]) for i in range(count))
        return round(total / count)
    return round(_frame_similarity((a.dhash, a.phash, a.pmask, a.color), (b.dhash, b.phash, b.pmask, b.color)))
