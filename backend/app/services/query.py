import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..db import q

VISIBLE = "m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL"
STACK_COLLAPSE = "(m.stack_id IS NULL OR m.id=(SELECT top_media_id FROM stacks s WHERE s.id=m.stack_id))"

SORTS = {
    "newest": ("m.created_ts", "DESC"),
    "oldest": ("m.created_ts", "ASC"),
    "added": ("m.imported_ts", "DESC"),
    "added_oldest": ("m.imported_ts", "ASC"),
    "name": ("m.name COLLATE NOCASE", "ASC"),
    "name_desc": ("m.name COLLATE NOCASE", "DESC"),
    "size": ("m.size", "DESC"),
    "size_small": ("m.size", "ASC"),
    "rating": ("m.rating", "DESC"),
    "edited": ("COALESCE(m.edited_ts, 0)", "DESC"),
    "viewed": ("COALESCE(m.viewed_ts, 0)", "DESC"),
}
SORT_ALIAS = {"m.name COLLATE NOCASE": "name", "m.created_ts": "created_ts", "m.imported_ts": "imported_ts",
              "m.size": "size", "m.rating": "rating", "COALESCE(m.edited_ts, 0)": "edited_ts", "COALESCE(m.viewed_ts, 0)": "viewed_ts"}

FLAGS = {
    "favorite": "m.favorite=1", "photo": "m.kind='image'", "video": "m.kind='video'",
    "screenshot": "m.is_screenshot=1", "screen_recording": "m.is_screen_rec=1", "raw": "m.is_raw=1",
    "live": "m.live_video_id IS NOT NULL", "panorama": "m.is_panorama=1", "selfie": "m.is_selfie=1",
    "portrait": "m.is_portrait=1", "slomo": "m.is_slomo=1", "burst": "m.burst_id IS NOT NULL",
    "edited": "m.edit_json IS NOT NULL", "rejected": "m.rejected=1", "not_rejected": "m.rejected=0",
    "located": "m.lat IS NOT NULL", "not_located": "m.lat IS NULL",
    "not_in_album": "m.id NOT IN (SELECT media_id FROM album_items)",
    "in_album": "m.id IN (SELECT media_id FROM album_items)",
    "has_keywords": "m.id IN (SELECT media_id FROM media_keywords)",
    "no_keywords": "m.id NOT IN (SELECT media_id FROM media_keywords)",
    "has_people": "m.id IN (SELECT media_id FROM faces WHERE person_id IS NOT NULL)",
    "titled": "COALESCE(m.title,'')<>''", "captioned": "COALESCE(m.caption,'')<>''",
    "viewed": "m.viewed_ts IS NOT NULL", "stacked": "m.stack_id IS NOT NULL",
    "has_text": "COALESCE(m.ocr_text,'')<>''",
    "animated": "m.is_animated=1", "timelapse": "m.is_timelapse=1", "cinematic": "m.is_cinematic=1",
    "spatial": "m.is_spatial=1", "long_exposure": "m.is_long_exposure=1",
}
TEXT_FIELDS = {
    "filename": "m.name", "title": "m.title", "caption": "m.caption", "camera": "(COALESCE(m.make,'')||' '||COALESCE(m.model,''))",
    "lens": "m.lens", "place": "(COALESCE(m.place,'')||' '||COALESCE(m.admin,'')||' '||COALESCE(m.country,''))",
    "text": "m.ocr_text", "folder": "m.rel_path", "alt_text": "m.alt_text",
}
NUM_FIELDS = {
    "rating": "m.rating", "iso": "m.iso", "aperture": "m.aperture", "focal": "m.focal", "shutter": "m.shutter",
    "size": "m.size", "width": "m.width", "height": "m.height", "duration": "m.duration",
    "created": "m.created_ts", "imported": "m.imported_ts",
}
OPS = {"=": "=", "!=": "<>", ">=": ">=", "<=": "<=", ">": ">", "<": "<"}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def keyword_ids(name_or_id: Any) -> List[int]:
    if isinstance(name_or_id, int) or (isinstance(name_or_id, str) and name_or_id.isdigit()):
        root = [int(name_or_id)]
    else:
        root = [r["id"] for r in q("SELECT id FROM keywords WHERE name=? COLLATE NOCASE", (str(name_or_id),))]
    ids, frontier = list(root), list(root)
    while frontier:
        marks = ",".join("?" * len(frontier))
        frontier = [r["id"] for r in q(f"SELECT id FROM keywords WHERE parent_id IN ({marks})", frontier) if r["id"] not in ids]
        ids.extend(frontier)
    return ids


def parse_date_range(text: str) -> Optional[Tuple[float, float]]:
    s = text.strip().lower()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        start = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return start.timestamp(), start.timestamp() + 86400
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        end = datetime(y + (mo == 12), mo % 12 + 1, 1)
        return datetime(y, mo, 1).timestamp(), end.timestamp()
    m = re.fullmatch(r"([a-z]+)\s+(\d{4})", s)
    if m and m.group(1)[:3] in {k[:3] for k in MONTHS}:
        mo = next(v for k, v in MONTHS.items() if k.startswith(m.group(1)[:3]))
        y = int(m.group(2))
        end = datetime(y + (mo == 12), mo % 12 + 1, 1)
        return datetime(y, mo, 1).timestamp(), end.timestamp()
    m = re.fullmatch(r"(\d{4})", s)
    if m and 1900 <= int(s) <= 2200:
        return datetime(int(s), 1, 1).timestamp(), datetime(int(s) + 1, 1, 1).timestamp()
    if s in MONTHS or (len(s) >= 3 and any(k.startswith(s) for k in MONTHS)):
        mo = MONTHS.get(s) or next(v for k, v in MONTHS.items() if k.startswith(s))
        return ("month", mo)  # type: ignore[return-value]
    if s in ("today", "yesterday", "this week", "last week", "this month", "last month", "this year", "last year"):
        now = datetime.now()
        day = datetime(now.year, now.month, now.day).timestamp()
        spans = {"today": (day, day + 86400), "yesterday": (day - 86400, day),
                 "this week": (day - 6 * 86400, day + 86400), "last week": (day - 13 * 86400, day - 6 * 86400),
                 "this month": (datetime(now.year, now.month, 1).timestamp(), day + 86400),
                 "last month": (datetime(now.year - (now.month == 1), (now.month - 2) % 12 + 1, 1).timestamp(),
                                datetime(now.year, now.month, 1).timestamp()),
                 "this year": (datetime(now.year, 1, 1).timestamp(), day + 86400),
                 "last year": (datetime(now.year - 1, 1, 1).timestamp(), datetime(now.year, 1, 1).timestamp())}
        return spans[s]
    return None


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def rule_sql(rule: Dict[str, Any]) -> Tuple[str, List[Any]]:
    field = str(rule.get("field", ""))
    op = str(rule.get("op", "="))
    value = rule.get("value")
    neg = op in ("not", "!=", "excludes")
    if field == "flag":
        sql = FLAGS.get(str(value))
        if not sql:
            return "1=1", []
        return (f"NOT ({sql})" if neg else sql), []
    if field in TEXT_FIELDS:
        col = TEXT_FIELDS[field]
        if op == "is":
            return f"COALESCE({col},'') = ? COLLATE NOCASE", [str(value or "")]
        if op == "starts":
            return f"COALESCE({col},'') LIKE ? ESCAPE '\\'", [str(value or "").replace("%", "\\%") + "%"]
        clause = f"COALESCE({col},'') LIKE ? ESCAPE '\\'"
        return (f"NOT ({clause})" if neg else clause), [_like(str(value or ""))]
    if field in NUM_FIELDS:
        col = NUM_FIELDS[field]
        if op == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
            return f"{col} >= ? AND {col} < ?", [float(value[0]), float(value[1])]
        return f"{col} {OPS.get(op, '=')} ?", [float(value or 0)]
    if field == "label":
        clause = "COALESCE(m.label,'') = ?"
        return (f"NOT ({clause})" if neg else clause), [str(value or "")]
    if field == "kind":
        return "m.kind = ?", [str(value)]
    if field == "album":
        clause = "m.id IN (SELECT media_id FROM album_items WHERE album_id=?)"
        return (f"NOT ({clause})" if neg else clause), [int(value)]
    if field == "person":
        clause = "m.id IN (SELECT media_id FROM faces WHERE person_id=?)"
        return (f"NOT ({clause})" if neg else clause), [int(value)]
    if field == "keyword":
        ids = keyword_ids(value)
        if not ids:
            return ("1=1" if neg else "0=1"), []
        marks = ",".join("?" * len(ids))
        clause = f"m.id IN (SELECT media_id FROM media_keywords WHERE keyword_id IN ({marks}))"
        return (f"NOT ({clause})" if neg else clause), ids
    if field == "subject":
        clause = "m.id IN (SELECT media_id FROM media_labels WHERE label=?)"
        return (f"NOT ({clause})" if neg else clause), [str(value)]
    if field == "group":
        people = [int(p) for p in str(value or "").split("-") if p.isdigit()][:6] or [-1]
        return " AND ".join("m.id IN (SELECT media_id FROM faces WHERE person_id=?)" for _ in people), people
    if field == "memory":
        return "m.id IN (SELECT media_id FROM memory_items WHERE memory_id=?)", [int(value)]
    if field == "search":
        fields = rule.get("fields")
        return text_sql(str(value or ""), list(fields) if isinstance(fields, list) else None)
    if field == "pet":
        clause = "m.pet_id = ?"
        return ("(m.pet_id IS NULL OR m.pet_id <> ?)" if neg else clause), [int(value)]
    if field == "visual":
        found = _visual_ids(str(value or ""))
        clause = f"m.id IN ({','.join('?' * len(found))})" if found else "0=1"
        return (f"NOT ({clause})" if neg and found else ("1=1" if neg else clause)), found
    if field == "similar":
        from . import clipsvc

        found = [mid for mid, _ in clipsvc.similar(int(value))][:5000] or [-1]
        return f"m.id IN ({','.join('?' * len(found))})", found
    if field == "batch":
        return "m.batch_id = ?", [int(value)]
    if field == "stack":
        return "m.stack_id = ?", [int(value)]
    if field == "date":
        span = parse_date_range(str(value or ""))
        if span is None:
            return "0=1", []
        if span[0] == "month":
            return "CAST(strftime('%m', m.created_ts, 'unixepoch', 'localtime') AS INTEGER) = ?", [span[1]]
        return "m.created_ts >= ? AND m.created_ts < ?", [span[0], span[1]]
    if field == "year":
        return "strftime('%Y', m.created_ts, 'unixepoch', 'localtime') = ?", [str(value)]
    if field == "on_this_day":
        now = datetime.now()
        return ("strftime('%m-%d', m.created_ts, 'unixepoch', 'localtime') = ? AND m.created_ts < ?",
                [now.strftime("%m-%d"), datetime(now.year, 1, 1).timestamp()])
    if field == "recent_days":
        return "m.created_ts >= ?", [time.time() - float(value or 30) * 86400]
    if field == "ids":
        ids = [int(v) for v in (value or [])][:5000] or [-1]
        return f"m.id IN ({','.join('?' * len(ids))})", ids
    if field == "bbox" and isinstance(value, (list, tuple)) and len(value) == 4:
        south, west, north, east = (float(v) for v in value)
        lon_sql = "m.lon >= ? AND m.lon <= ?" if west <= east else "(m.lon >= ? OR m.lon <= ?)"
        return (f"m.location_hidden = 0 AND m.lat >= ? AND m.lat <= ? AND {lon_sql}", [south, north, west, east])
    return "1=1", []


def where(spec: Dict[str, Any]) -> Tuple[str, List[Any]]:
    clauses, params = [VISIBLE], []
    if not spec.get("expand_stacks"):
        clauses.append(STACK_COLLAPSE)
    rules = spec.get("rules") or []
    if rules:
        parts = []
        for rule in rules:
            if rule.get("rules"):
                sub_sql, sub_params = where({"rules": rule["rules"], "match": rule.get("match", "all"), "expand_stacks": True, "_inner": True})
                parts.append(f"({sub_sql})")
                params.extend(sub_params)
                continue
            sql, ps = rule_sql(rule)
            parts.append(f"({sql})")
            params.extend(ps)
        joiner = " OR " if spec.get("match") == "any" else " AND "
        clauses.append("(" + joiner.join(parts) + ")")
    text = (spec.get("text") or "").strip()
    if text:
        sql, ps = text_sql(text, spec.get("fields"))
        clauses.append(sql)
        params.extend(ps)
    if spec.get("_inner"):
        return " AND ".join(clauses[2 if not spec.get("expand_stacks") else 1:]) or "1=1", params
    return " AND ".join(clauses), params


TEXT_SCOPES = ("name", "title", "caption", "keywords", "ocr", "people", "albums", "places", "camera", "subjects", "dates", "visual")


def text_sql(text: str, fields: Optional[List[str]] = None) -> Tuple[str, List[Any]]:
    wanted = set(fields or TEXT_SCOPES)
    terms = [t for t in re.findall(r'"[^"]+"|\S+', text) if t]
    span = parse_date_range(text) if "dates" in wanted else None
    if span is not None:
        sql, ps = rule_sql({"field": "date", "value": text})
        return f"({sql})", ps
    out, params = [], []
    for raw in terms:
        term = raw.strip('"')
        like = _like(term)
        alts = []
        if "name" in wanted:
            alts.append("m.name LIKE ? ESCAPE '\\'")
            params.append(like)
        if "title" in wanted:
            alts.append("COALESCE(m.title,'') LIKE ? ESCAPE '\\'")
            params.append(like)
        if "caption" in wanted:
            alts.append("COALESCE(m.caption,'')||' '||COALESCE(m.alt_text,'') LIKE ? ESCAPE '\\'")
            params.append(like)
        if "ocr" in wanted:
            alts.append("COALESCE(m.ocr_text,'') LIKE ? ESCAPE '\\'")
            params.append(like)
        if "camera" in wanted:
            alts.append("COALESCE(m.make,'')||' '||COALESCE(m.model,'')||' '||COALESCE(m.lens,'') LIKE ? ESCAPE '\\'")
            params.append(like)
        if "places" in wanted:
            alts.append("COALESCE(m.place,'')||' '||COALESCE(m.admin,'')||' '||COALESCE(m.country,'') LIKE ? ESCAPE '\\'")
            params.append(like)
        if "keywords" in wanted:
            alts.append("m.id IN (SELECT mk.media_id FROM media_keywords mk JOIN keywords k ON k.id=mk.keyword_id WHERE k.name LIKE ? ESCAPE '\\')")
            params.append(like)
        if "people" in wanted:
            alts.append("m.id IN (SELECT f.media_id FROM faces f JOIN people p ON p.id=f.person_id WHERE COALESCE(p.name,'') LIKE ? ESCAPE '\\')")
            params.append(like)
        if "albums" in wanted:
            alts.append("m.id IN (SELECT ai.media_id FROM album_items ai JOIN albums a ON a.id=ai.album_id WHERE a.is_private=0 AND a.name LIKE ? ESCAPE '\\')")
            params.append(like)
        if "subjects" in wanted:
            alts.append("m.id IN (SELECT media_id FROM media_labels WHERE label LIKE ? ESCAPE '\\')")
            params.append(like)
        if "dates" in wanted:
            span_one = parse_date_range(term)
            if span_one is not None and span_one[0] != "month":
                alts.append("(m.created_ts >= ? AND m.created_ts < ?)")
                params.extend([span_one[0], span_one[1]])
        if alts:
            out.append("(" + " OR ".join(alts) + ")")
    joined = ("(" + " AND ".join(out) + ")") if out else "1=1"
    if "visual" in wanted and out:
        found = _visual_ids(text)
        if found:
            joined = f"({joined} OR m.id IN ({','.join('?' * len(found))}))"
            params.extend(found)
    return joined, params


def _visual_ids(text: str) -> List[int]:
    from . import clipsvc

    try:
        return [mid for mid, _ in clipsvc.search(text)][:5000]
    except Exception:
        return []


def page(spec: Dict[str, Any], limit: int = 400, cursor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    sort = spec.get("sort") or "newest"
    col, direction = SORTS.get(sort, SORTS["newest"])
    sql, params = where(spec)
    cmp = "<" if direction == "DESC" else ">"
    if cursor and "v" in cursor and "id" in cursor:
        sql += f" AND ({col} {cmp} ? OR ({col} = ? AND m.id {cmp} ?))"
        params += [cursor["v"], cursor["v"], cursor["id"]]
    alias = SORT_ALIAS[col]
    rows = q(
        f"SELECT m.*, {col} AS _sortv FROM media m WHERE {sql} ORDER BY {col} {direction}, m.id {direction} LIMIT ?",
        (*params, limit),
    )
    nxt = None
    if len(rows) == limit:
        nxt = {"v": rows[-1]["_sortv"], "id": rows[-1]["id"], "k": alias}
    return {"rows": rows, "next": nxt}


def ids(spec: Dict[str, Any], limit: int = 100000) -> List[int]:
    sql, params = where(spec)
    col, direction = SORTS.get(spec.get("sort") or "newest", SORTS["newest"])
    return [r["id"] for r in q(f"SELECT m.id FROM media m WHERE {sql} ORDER BY {col} {direction}, m.id {direction} LIMIT ?", (*params, limit))]


def count(spec: Dict[str, Any]) -> int:
    sql, params = where(spec)
    return q(f"SELECT COUNT(*) AS n FROM media m WHERE {sql}", params)[0]["n"]


def parse_spec(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        spec = json.loads(raw)
    except ValueError:
        return {}
    return spec if isinstance(spec, dict) else {}
