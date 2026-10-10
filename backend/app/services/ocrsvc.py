
from ..dedup.visual import _find_tool
import subprocess
import tempfile
from typing import Any, Dict, Optional

from ..db import ex, q
from . import libraryfs, thumbs


def tesseract_path() -> Optional[str]:
    return _find_tool("tesseract") or None


_RAPID = None
_RAPID_TRIED = False


def _rapid_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


def _rapid_engine():
    global _RAPID, _RAPID_TRIED
    if not _RAPID_TRIED:
        _RAPID_TRIED = True
        try:
            from rapidocr_onnxruntime import RapidOCR

            try:
                _RAPID = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
            except TypeError:
                _RAPID = RapidOCR()
        except Exception:
            _RAPID = None
    return _RAPID


def release_engine() -> None:
    """Drop the ONNX sessions after a scan so the app returns to idle weight."""
    global _RAPID, _RAPID_TRIED
    _RAPID = None
    _RAPID_TRIED = False
    import gc

    gc.collect()


def engine_name() -> Optional[str]:
    if _rapid_available():
        return "rapidocr"
    if tesseract_path():
        return "tesseract"
    return None


def status() -> Dict[str, Any]:
    pending = q(
        "SELECT COUNT(*) AS n FROM media WHERE ocr_text IS NULL AND trashed_ts IS NULL AND live_of IS NULL AND kind='image'"
    )[0]["n"]
    return {"engine": engine_name(), "tesseract": bool(tesseract_path()), "pending": pending}


def _extract(image_path: str) -> str:
    rapid = _rapid_engine()
    if rapid is not None:
        try:
            import numpy as np
            from PIL import Image

            with Image.open(image_path) as img:
                arr = np.array(img.convert("RGB"))
            results, _ = rapid(arr)
            if results:
                return " ".join(part[1] for part in results if part[1])
            return ""
        except Exception:
            pass
    binary = tesseract_path()
    if not binary:
        return ""
    try:
        proc = subprocess.run(
            [binary, image_path, "stdout", "--psm", "3"],
            capture_output=True, timeout=45, text=True,
        )
        return " ".join(proc.stdout.split()) if proc.returncode == 0 else ""
    except Exception:
        return ""


def scan_job(state: Dict[str, Any]) -> None:
    if engine_name() is None:
        raise RuntimeError("No text engine available. The bundled model failed to load & tesseract is not installed.")
    counts = {"scanned": 0, "with_text": 0, "videos": 0}
    state["counts"] = counts
    import time as _time

    rows = q("SELECT id, rel_path, kind FROM media WHERE ocr_text IS NULL AND trashed_ts IS NULL AND live_of IS NULL ORDER BY id")
    try:
        for row in rows:
            text = ""
            if row["kind"] == "image":
                text = _extract(libraryfs.abs_path(row["rel_path"]))
            else:
                poster = thumbs.ensure_thumb(row["id"], row["rel_path"], "video", 768)
                if poster:
                    text = _extract(poster)
                counts["videos"] += 1
            ex("UPDATE media SET ocr_text=? WHERE id=?", (text, row["id"]))
            counts["scanned"] += 1
            if text:
                counts["with_text"] += 1
            _time.sleep(0.002)
    finally:
        release_engine()


def _tmpdir() -> str:
    return tempfile.gettempdir()
