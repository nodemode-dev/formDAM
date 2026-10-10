import hashlib
import os
import threading
from collections import OrderedDict
from typing import Optional

import numpy as np

from ..config import models_dir

MODEL = "inpainting_lama_2025jan.onnx"
SIZE = 512

MEMO = 6

_lock = threading.Lock()
_mlock = threading.Lock()
_session = None
_memo: "OrderedDict[str, np.ndarray]" = OrderedDict()


def model_path() -> str:
    return os.path.join(models_dir(), MODEL)


def ready() -> bool:
    if not os.path.isfile(model_path()):
        return False
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def _engine():
    global _session
    with _lock:
        if _session is None:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) - 1))
            _session = ort.InferenceSession(model_path(), sess_options=opts, providers=["CPUExecutionProvider"])
        return _session


def _run(patch: np.ndarray, mask: np.ndarray) -> np.ndarray:
    import cv2

    h, w = patch.shape[:2]
    img = cv2.resize(patch, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    m = (cv2.resize(mask, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)
    out = _engine().run(["output"], {"image": img.transpose(2, 0, 1)[None], "mask": m[None, None]})[0][0]
    out = np.clip(out.transpose(1, 2, 0), 0, 255).astype(np.uint8)
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_CUBIC)


def warm() -> None:
    if ready() and _session is None:
        threading.Thread(target=_engine, daemon=True).start()


def _key(rgb: np.ndarray, mask: np.ndarray) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(str(rgb.shape).encode())
    h.update(np.ascontiguousarray(rgb[::4, ::4]).tobytes())
    h.update(np.ascontiguousarray(mask).tobytes())
    return h.hexdigest()


def inpaint(rgb: np.ndarray, mask: np.ndarray) -> Optional[np.ndarray]:
    if not ready():
        return None
    key = _key(rgb, mask)
    with _mlock:
        hit = _memo.get(key)
        if hit is not None:
            _memo.move_to_end(key)
            return hit.copy()
    result = _inpaint(rgb, mask)
    with _mlock:
        _memo[key] = result
        while len(_memo) > MEMO:
            _memo.popitem(last=False)
    return result.copy()


def _inpaint(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    import cv2

    h, w = rgb.shape[:2]
    grown = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=2)
    count, labels, stats, _ = cv2.connectedComponentsWithStats((grown > 0).astype(np.uint8))
    result = rgb.copy()
    for i in range(1, count):
        x, y, bw, bh, _ = stats[i]
        big = max(bw, bh)
        side = int(big + 2 * max(48, big * 0.5))
        cx, cy = x + bw / 2, y + bh / 2
        x0, y0 = int(max(0, min(w - side, cx - side / 2))), int(max(0, min(h - side, cy - side / 2)))
        x1, y1 = int(min(w, x0 + side)), int(min(h, y0 + side))
        region = (labels[y0:y1, x0:x1] == i).astype(np.uint8) * 255
        patch = result[y0:y1, x0:x1]
        filled = _run(patch, region)
        soft = cv2.GaussianBlur(region.astype(np.float32) / 255.0, (0, 0), sigmaX=2.0)[..., None]
        result[y0:y1, x0:x1] = (filled * soft + patch * (1 - soft)).astype(np.uint8)
    return result
