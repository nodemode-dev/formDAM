# Adapted from formlit backend/app/services/rename.py (Apache-2.0, nodemode-ai); see LICENSES.md.
import os
import re
from datetime import datetime
from typing import Any, Dict

TOKENS = {
    "name": "Original file name without its extension",
    "ext": "Original extension, lower case",
    "seq": "Sequence number; {seq:4} pads to 4 digits",
    "num": "Number found at the end of the original name",
    "date": "Capture date; {date:%Y-%m-%d} takes a strftime pattern",
    "year": "Capture year", "month": "Capture month", "day": "Capture day",
    "hour": "Capture hour", "minute": "Capture minute", "second": "Capture second",
    "camera": "Camera model", "lens": "Lens", "iso": "ISO", "focal": "Focal length in mm", "aperture": "Aperture",
    "rating": "Star rating", "label": "Colour label", "title": "Title", "place": "Place name", "country": "Country",
    "custom": "Custom text passed with the template",
}

_TOKEN = re.compile(r"\{([a-z]+)(?::([^}]*))?\}")
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe(text: str) -> str:
    return _UNSAFE.sub("-", text).strip().strip(".") or "untitled"


def expand(template: str, row: Dict[str, Any], seq: int = 1, custom: str = "") -> str:
    stem, ext = os.path.splitext(row.get("name") or "photo")
    ext = ext.lower().lstrip(".")
    when = datetime.fromtimestamp(row["created_ts"]) if row.get("created_ts") else None
    found = re.search(r"(\d+)$", stem)

    def one(m: re.Match) -> str:
        key, arg = m.group(1), m.group(2)
        if key == "name":
            return stem
        if key == "ext":
            return ext
        if key == "seq":
            return str(seq).zfill(int(arg) if arg and arg.isdigit() else 1)
        if key == "num":
            return found.group(1) if found else str(seq)
        if key in ("date", "year", "month", "day", "hour", "minute", "second"):
            if when is None:
                return "undated"
            fmt = {"date": arg or "%Y%m%d", "year": "%Y", "month": "%m", "day": "%d",
                   "hour": "%H", "minute": "%M", "second": "%S"}[key]
            return when.strftime(fmt)
        if key == "camera":
            return str(row.get("model") or row.get("make") or "camera")
        if key == "lens":
            return str(row.get("lens") or "lens")
        if key == "iso":
            return str(row.get("iso") or "")
        if key == "focal":
            return f"{row['focal']:.0f}mm" if row.get("focal") else ""
        if key == "aperture":
            return f"f{row['aperture']:.1f}" if row.get("aperture") else ""
        if key == "rating":
            return str(row.get("rating") or 0)
        if key == "label":
            return str(row.get("label") or "")
        if key == "title":
            return str(row.get("title") or "")
        if key == "place":
            return str(row.get("place") or "")
        if key == "country":
            return str(row.get("country") or "")
        if key == "custom":
            return custom
        return m.group(0)

    out = safe(_TOKEN.sub(one, template).replace("/", "-").replace("\\", "-"))
    return out
