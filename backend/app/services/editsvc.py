import json
from typing import Any, Dict, List, Optional

from PIL import Image

from ..db import q1


def edits_of(media_id: int) -> List[Dict[str, Any]]:
    row = q1("SELECT edit_json FROM media WHERE id=?", (media_id,))
    if row is None or not row["edit_json"]:
        return []
    try:
        ops = json.loads(row["edit_json"])
    except ValueError:
        return []
    return ops if isinstance(ops, list) else []


def apply_edits(img: Image.Image, ops: List[Dict[str, Any]]) -> Image.Image:
    return img


def render_still(media_id: int, src: Any, max_long: Optional[int]) -> Optional[Image.Image]:
    ops = edits_of(media_id)
    if not ops:
        return None
    from . import decode

    row = q1("SELECT name FROM media WHERE id=?", (media_id,))
    base = decode.open_image(src, row["name"] if row else "", max_long=None if max_long is None else max_long * 2, develop=True)
    if base is None:
        return None
    out = apply_edits(base, ops)
    if max_long and max(out.size) > max_long:
        out.thumbnail((max_long, max_long), Image.Resampling.LANCZOS)
    return out
