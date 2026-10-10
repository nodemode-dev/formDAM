import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..db import q1

STAGES = ("retouch", "geometry", "tone", "markup")
LIGHT = ("exposure", "brilliance", "highlights", "shadows", "brightness", "contrast", "blacks")
COLOR = ("saturation", "vibrance", "warmth", "tint")
DETAIL = ("definition", "sharpen", "noise", "vignette")
FILTERS: Dict[str, Dict[str, float]] = {
    "vivid": {"saturation": 0.25, "vibrance": 0.15, "contrast": 0.12},
    "vivid_warm": {"saturation": 0.22, "vibrance": 0.12, "contrast": 0.1, "warmth": 0.3},
    "vivid_cool": {"saturation": 0.22, "vibrance": 0.12, "contrast": 0.1, "warmth": -0.3},
    "dramatic": {"contrast": 0.35, "saturation": -0.12, "shadows": -0.2, "highlights": -0.25, "definition": 0.3},
    "dramatic_warm": {"contrast": 0.32, "saturation": -0.05, "shadows": -0.2, "highlights": -0.25, "warmth": 0.3, "definition": 0.25},
    "dramatic_cool": {"contrast": 0.32, "saturation": -0.05, "shadows": -0.2, "highlights": -0.25, "warmth": -0.3, "definition": 0.25},
    "mono": {"bw": 1.0},
    "silvertone": {"bw": 1.0, "contrast": 0.15, "brightness": 0.08, "tone": 0.2},
    "noir": {"bw": 1.0, "contrast": 0.5, "blacks": 0.2, "definition": 0.2},
}


def edits_of(media_id: int) -> Dict[str, Any]:
    row = q1("SELECT edit_json FROM media WHERE id=?", (media_id,))
    if row is None or not row["edit_json"]:
        return {}
    try:
        state = json.loads(row["edit_json"])
    except ValueError:
        return {}
    return state if isinstance(state, dict) else {}


def apply_edits(img: Image.Image, state: Dict[str, Any], stages: Iterable[str] = STAGES) -> Image.Image:
    stages = set(stages)
    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    img = img.convert("RGB")
    if "retouch" in stages and state.get("retouch"):
        img = _retouch(img, state["retouch"])
    if "geometry" in stages:
        img = _geometry(img, state)
        if alpha is not None:
            alpha = _geometry(alpha, state)
    if "tone" in stages and _has_tone(state):
        img = _tone(img, state)
    if "markup" in stages and state.get("markup"):
        img = _markup(img, state["markup"])
    if alpha is not None and alpha.size == img.size:
        img.putalpha(alpha)
    return img


def render_still(media_id: int, src: Any, max_long: Optional[int]) -> Optional[Image.Image]:
    ops = edits_of(media_id)
    if not ops:
        return None
    from . import decode

    row = q1("SELECT name FROM media WHERE id=?", (media_id,))
    base = long_exposure(media_id, None if max_long is None else max_long * 2) if ops.get("effect") == "long_exposure" else None
    if base is None:
        base = decode.open_image(src, row["name"] if row else "", max_long=None if max_long is None else max_long * 2, develop=True,
                                 raw_opts=ops.get("raw") or None)
    if base is None:
        return None
    out = apply_edits(base, ops)
    if max_long and max(out.size) > max_long:
        out.thumbnail((max_long, max_long), Image.Resampling.LANCZOS)
    return out


def _f(state: Dict[str, Any], group: str, key: str, lo: float = -1.0, hi: float = 1.0) -> float:
    try:
        value = float((state.get(group) or {}).get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(lo, min(hi, value))


def effective(state: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key in LIGHT:
        out[key] = _f(state, "light", key, -2.0 if key == "exposure" else -1.0, 2.0 if key == "exposure" else 1.0)
    for key in COLOR:
        out[key] = _f(state, "color", key)
    for key in DETAIL:
        out[key] = _f(state, "detail", key, 0.0 if key in ("sharpen", "noise") else -1.0)
    out["bw"] = _f(state, "bw", "intensity", 0.0, 1.0)
    out["tone"] = _f(state, "bw", "tone")
    flt = FILTERS.get(str((state.get("filter") or {}).get("name", "")))
    if flt:
        amount = _f(state, "filter", "amount", 0.0, 1.0) if "amount" in (state.get("filter") or {}) else 1.0
        for key, value in flt.items():
            out[key] = out.get(key, 0.0) + value * amount
            if key == "bw":
                out[key] = min(1.0, out[key])
    if out["brilliance"]:
        b = out["brilliance"]
        out["shadows"] += b * 0.5
        out["highlights"] -= b * 0.35
        out["contrast"] += b * 0.1
    return out


def _has_tone(state: Dict[str, Any]) -> bool:
    eff = effective(state)
    return any(abs(v) > 1e-4 for v in eff.values()) or bool(state.get("levels")) or bool(state.get("curves"))


def _smooth(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _lum(a: np.ndarray, weights: Tuple[float, float, float] = (0.299, 0.587, 0.114)) -> np.ndarray:
    return a[..., 0] * weights[0] + a[..., 1] * weights[1] + a[..., 2] * weights[2]


def _blur(channel: np.ndarray, sigma: float) -> np.ndarray:
    import cv2

    return cv2.GaussianBlur(channel, (0, 0), sigmaX=max(0.5, sigma))


def _tone(img: Image.Image, state: Dict[str, Any]) -> Image.Image:
    e = effective(state)
    a = np.asarray(img, dtype=np.float32) / 255.0
    if e["exposure"]:
        a = a * (2.0 ** e["exposure"])
    if e["brightness"]:
        a = np.clip(a, 0, None) ** (2.0 ** (-e["brightness"] * 0.8))
    if e["highlights"] or e["shadows"]:
        lum = _lum(np.clip(a, 0, 1))[..., None]
        a = a + e["highlights"] * 0.35 * _smooth(0.45, 1.0, lum) * (lum if e["highlights"] < 0 else (1 - lum))
        a = a + e["shadows"] * 0.4 * (1 - _smooth(0.0, 0.55, lum)) * ((1 - lum) if e["shadows"] > 0 else lum)
    if e["contrast"]:
        a = (a - 0.5) * (1 + e["contrast"]) + 0.5
    if e["blacks"]:
        cut = e["blacks"] * 0.12
        a = (a - cut) / (1 - cut) if cut > 0 else a * (1 + cut) - cut
    levels = state.get("levels") or {}
    if levels:
        lo = float(levels.get("black", 0) or 0)
        hi = float(levels.get("white", 1) or 1)
        gamma = max(0.1, float(levels.get("gamma", 1) or 1))
        a = np.clip((a - lo) / max(1e-3, hi - lo), 0, 1) ** (1.0 / gamma)
    curves = state.get("curves") or {}
    for idx, key in enumerate(("rgb", "r", "g", "b")):
        pts = curves.get(key)
        if not pts or len(pts) < 2:
            continue
        pts = sorted((float(p[0]), float(p[1])) for p in pts)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if key == "rgb":
            a = np.interp(np.clip(a, 0, 1), xs, ys).astype(np.float32)
        else:
            a[..., idx - 1] = np.interp(np.clip(a[..., idx - 1], 0, 1), xs, ys)
    if e["saturation"] or e["vibrance"]:
        lum = _lum(a)[..., None]
        sat = a.max(axis=2, keepdims=True) - a.min(axis=2, keepdims=True)
        gain = 1 + e["saturation"] + e["vibrance"] * (1 - np.clip(sat * 1.6, 0, 1))
        a = lum + (a - lum) * gain
    if e["warmth"] or e["tint"]:
        a = a + np.array([e["warmth"] * 0.08 + e["tint"] * 0.04, -e["tint"] * 0.06, -e["warmth"] * 0.08 + e["tint"] * 0.04], dtype=np.float32)
    if e["bw"] > 0:
        t = e["tone"]
        weights = (0.299 + 0.2 * t, 0.587, 0.114 - 0.1 * t)
        total = sum(weights)
        gray = _lum(a, tuple(w / total for w in weights))[..., None]
        a = a * (1 - e["bw"]) + gray * e["bw"]
    short = min(a.shape[0], a.shape[1])
    if e["definition"]:
        lum = _lum(a)
        a = a + (e["definition"] * 0.7 * (lum - _blur(lum, short * 0.02)))[..., None]
    if e["noise"] > 0:
        import cv2

        u8 = (np.clip(a, 0, 1) * 255).astype(np.uint8)
        a = cv2.bilateralFilter(u8, 0, 12 + e["noise"] * 40, 2 + e["noise"] * 6).astype(np.float32) / 255.0
    if e["sharpen"] > 0:
        a = a + e["sharpen"] * 1.2 * (a - np.stack([_blur(a[..., c], max(1.0, short / 900)) for c in range(3)], axis=2))
    if e["vignette"]:
        h, w = a.shape[:2]
        yy, xx = np.ogrid[:h, :w]
        dist = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
        mask = _smooth(0.35, 1.0, dist.astype(np.float32))[..., None]
        a = a * (1 - e["vignette"] * 0.75 * mask) if e["vignette"] > 0 else a + (-e["vignette"]) * 0.5 * mask * (1 - a)
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def _lens(img: Image.Image, lens: Dict[str, Any]) -> Image.Image:
    import cv2

    k = max(-1.0, min(1.0, float(lens.get("distortion", 0) or 0))) * 0.25
    vig = max(-1.0, min(1.0, float(lens.get("vignette", 0) or 0)))
    if not k and not vig:
        return img
    mode = img.mode
    a = np.asarray(img.convert("RGB") if mode not in ("RGB", "L") else img)
    h, w = a.shape[:2]
    yy, xx = np.indices((h, w), dtype=np.float32)
    cx, cy, norm = (w - 1) / 2.0, (h - 1) / 2.0, math.hypot(w / 2.0, h / 2.0)
    nx, ny = (xx - cx) / norm, (yy - cy) / norm
    r2 = nx * nx + ny * ny
    if k:
        f = 1 + k * r2
        a = cv2.remap(a, (cx + nx * f * norm).astype(np.float32), (cy + ny * f * norm).astype(np.float32),
                      cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    if vig and a.ndim == 3:
        gain = (1 + vig * 0.8 * r2 * 2)[..., None]
        a = np.clip(a.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    return Image.fromarray(a, "RGB" if a.ndim == 3 else "L")


def _geometry(img: Image.Image, state: Dict[str, Any]) -> Image.Image:
    if state.get("lens"):
        img = _lens(img, state["lens"])
    geo = state.get("geometry") or {}
    turns = int(geo.get("rotate", 0) or 0) % 360
    if turns == 90:
        img = img.transpose(Image.Transpose.ROTATE_90)
    elif turns == 180:
        img = img.transpose(Image.Transpose.ROTATE_180)
    elif turns == 270:
        img = img.transpose(Image.Transpose.ROTATE_270)
    if geo.get("flipH"):
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if geo.get("flipV"):
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    angle = max(-45.0, min(45.0, float(geo.get("straighten", 0) or 0)))
    if abs(angle) > 0.01:
        w, h = img.size
        rad = math.radians(abs(angle))
        scale = max((w * math.cos(rad) + h * math.sin(rad)) / w, (w * math.sin(rad) + h * math.cos(rad)) / h)
        rotated = img.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=False)
        cw, ch = w / scale, h / scale
        img = rotated.crop((round((w - cw) / 2), round((h - ch) / 2), round((w + cw) / 2), round((h + ch) / 2)))
    crop = geo.get("crop")
    if crop:
        w, h = img.size
        x = max(0.0, min(1.0, float(crop.get("x", 0))))
        y = max(0.0, min(1.0, float(crop.get("y", 0))))
        cw = max(0.01, min(1.0 - x, float(crop.get("w", 1))))
        ch = max(0.01, min(1.0 - y, float(crop.get("h", 1))))
        img = img.crop((round(x * w), round(y * h), round((x + cw) * w), round((y + ch) * h)))
    return img


def _retouch(img: Image.Image, spots: List[Dict[str, Any]]) -> Image.Image:
    import cv2

    a = np.asarray(img.convert("RGB"))
    h, w = a.shape[:2]
    short = min(w, h)
    mask = np.zeros((h, w), dtype=np.uint8)
    for spot in spots[:400]:
        try:
            r = max(1.0, float(spot.get("r", 0.02)) * short)
            if spot.get("points"):
                pts = np.array([[float(p[0]) * w, float(p[1]) * h] for p in spot["points"][:2000]], dtype=np.int32)
                if len(pts) == 1:
                    cv2.circle(mask, (int(pts[0][0]), int(pts[0][1])), int(r), 255, -1)
                else:
                    cv2.polylines(mask, [pts], False, 255, thickness=max(1, int(r * 2)), lineType=cv2.LINE_AA)
                continue
            cx, cy = float(spot["x"]) * w, float(spot["y"]) * h
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        cv2.circle(mask, (int(cx), int(cy)), int(r), 255, -1)
    if not mask.any():
        return img
    from . import cleanup

    filled = cleanup.inpaint(a, mask)
    if filled is not None:
        return Image.fromarray(filled)
    radius = max(3, int(short * 0.01))
    out = cv2.inpaint(cv2.cvtColor(a, cv2.COLOR_RGB2BGR), mask, radius, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def _color(value: Any) -> Tuple[int, int, int]:
    text = str(value or "#ff3b30").lstrip("#")
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (255, 59, 48)


def _markup(img: Image.Image, shapes: List[Dict[str, Any]]) -> Image.Image:
    img = img.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    short = min(w, h)
    for shape in shapes[:500]:
        color = _color(shape.get("color"))
        width = max(1, int(float(shape.get("width", 0.006) or 0.006) * short))
        pts = [(float(p[0]) * w, float(p[1]) * h) for p in shape.get("points") or [] if len(p) >= 2]
        kind = shape.get("type")
        if kind == "pen" and len(pts) > 1:
            draw.line(pts, fill=color, width=width, joint="curve")
        elif kind == "rect" and len(pts) == 2:
            (x0, y0), (x1, y1) = pts
            draw.rectangle((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), outline=color, width=width)
        elif kind == "ellipse" and len(pts) == 2:
            (x0, y0), (x1, y1) = pts
            draw.ellipse((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), outline=color, width=width)
        elif kind == "arrow" and len(pts) == 2:
            (x0, y0), (x1, y1) = pts
            draw.line((x0, y0, x1, y1), fill=color, width=width)
            ang = math.atan2(y1 - y0, x1 - x0)
            head = width * 4
            for side in (-0.45, 0.45):
                draw.line((x1, y1, x1 - head * math.cos(ang + side), y1 - head * math.sin(ang + side)), fill=color, width=width)
        elif kind == "text" and pts and shape.get("text"):
            size = max(8, int(float(shape.get("size", 0.05) or 0.05) * short))
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:
                font = ImageFont.load_default()
            draw.text(pts[0], str(shape["text"])[:400], fill=color, font=font)
    return img


def auto_enhance(img: Image.Image) -> Dict[str, Any]:
    small = img.convert("RGB").copy()
    small.thumbnail((512, 512))
    a = np.asarray(small, dtype=np.float32) / 255.0
    lum = _lum(a)
    lo, mid, hi = (float(np.percentile(lum, p)) for p in (1, 50, 99))
    exposure = float(np.clip(math.log2(0.45 / max(mid, 0.02)) * 0.5, -1.0, 1.0))
    sat = float(np.mean(a.max(axis=2) - a.min(axis=2)))
    r, g, b = (float(a[..., i].mean()) for i in range(3))
    return {
        "light": {"exposure": round(exposure, 2), "brilliance": 0.15,
                  "highlights": round(float(np.clip((0.97 - hi) * 2 if hi < 0.97 else -(hi - 0.97) * 6, -0.6, 0.3)), 2),
                  "shadows": round(float(np.clip((0.06 - lo) * 4 if lo > 0.06 else 0.1, -0.3, 0.4)), 2),
                  "contrast": round(float(np.clip((0.75 - (hi - lo)) * 0.6, -0.2, 0.3)), 2)},
        "color": {"vibrance": round(float(np.clip((0.22 - sat) * 1.5, -0.2, 0.35)), 2),
                  "warmth": round(float(np.clip((b - r) * 1.5, -0.3, 0.3)), 2),
                  "tint": round(float(np.clip((g - (r + b) / 2) * 1.5, -0.3, 0.3)), 2)},
    }


LE_FRAMES = 90


def long_exposure(media_id: int, max_long: Optional[int]) -> Optional[Image.Image]:
    import os

    from ..config import cache_dir

    row = q1("SELECT live_video_id FROM media WHERE id=?", (media_id,))
    if row is None or not row["live_video_id"]:
        return None
    folder = os.path.join(cache_dir(), "effects")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, f"{media_id}_le.png")
    if not os.path.isfile(out):
        made = _average_frames(row["live_video_id"])
        if made is None:
            return None
        made.save(out)
    img = Image.open(out)
    img.load()
    if max_long and max(img.size) > max_long:
        img.thumbnail((max_long, max_long), Image.Resampling.LANCZOS)
    return img


def _average_frames(video_id: int) -> Optional[Image.Image]:
    import subprocess

    import cv2

    from ..dedup.visual import ffmpeg_path
    from . import libraryfs

    vrow = q1("SELECT rel_path, width, height FROM media WHERE id=?", (video_id,))
    binary = ffmpeg_path()
    if vrow is None or not binary:
        return None
    w, h = int(vrow["width"] or 0), int(vrow["height"] or 0)
    if not (w and h):
        return None
    scale = min(1.0, 2048 / max(w, h))
    w2, h2 = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    done = subprocess.run([binary, "-v", "error", "-i", libraryfs.abs_path(vrow["rel_path"]), "-frames:v", str(LE_FRAMES),
                           "-vf", f"scale={w2}:{h2}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=120)
    raw = done.stdout
    size = w2 * h2 * 3
    count = len(raw) // size
    if count < 2:
        return None
    frames = np.frombuffer(raw[: count * size], dtype=np.uint8).reshape(count, h2, w2, 3)
    ref = cv2.cvtColor(frames[count // 2], cv2.COLOR_RGB2GRAY)
    small = cv2.resize(ref, (w2 // 4, h2 // 4)).astype(np.float32)
    acc = np.zeros((h2, w2, 3), dtype=np.float64)
    for frame in frames:
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), (w2 // 4, h2 // 4)).astype(np.float32)
            _, warp = cv2.findTransformECC(small, gray, warp, cv2.MOTION_TRANSLATION,
                                           (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 1e-4), None, 3)
            warp[:, 2] *= 4
            frame = cv2.warpAffine(frame, warp, (w2, h2), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT)
        except cv2.error:
            pass
        acc += frame
    return Image.fromarray(np.clip(acc / count, 0, 255).astype(np.uint8), "RGB")
