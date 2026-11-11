import os
import re
from typing import Iterator, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from ..db import ex, media_dict, now, q, q1
from ..services import libraryfs, thumbs
from .guard import ensure_visible
from .revalidate import NO_STORE, file_tag, must_not_store, revalidated_file, revalidated_headers, tag_matches

router = APIRouter()
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
STREAM_CHUNK = 512 * 1024

FILTERS = {
    "all": ("", "created_ts DESC, id DESC"),
    "favorites": ("AND favorite=1", "created_ts DESC, id DESC"),
    "photos": ("AND kind='image'", "created_ts DESC, id DESC"),
    "videos": ("AND kind='video'", "created_ts DESC, id DESC"),
    "screenshots": ("AND is_screenshot=1", "created_ts DESC, id DESC"),
    "screenrecs": ("AND is_screen_rec=1", "created_ts DESC, id DESC"),
    "not_in_album": ("AND id NOT IN (SELECT media_id FROM album_items)", "created_ts DESC, id DESC"),
    "recently_saved": ("", "imported_ts DESC, id DESC"),
    "recently_viewed": ("AND viewed_ts IS NOT NULL", "viewed_ts DESC, id DESC"),
}


@router.get("/media")
def list_media(
    filter: str = Query("all"),
    order: str = Query("newest", pattern="^(newest|oldest)$"),
    limit: int = Query(400, ge=1, le=1000),
    before: Optional[float] = Query(None),
    before_id: Optional[int] = Query(None),
):
    clause, base_order = FILTERS.get(filter, FILTERS["all"])
    if order == "oldest":
        base_order = base_order.replace("DESC", "ASC")
    cursor_field = base_order.split(" ", 1)[0]
    comparator = ">" if order == "oldest" else "<"
    params = []
    cursor_sql = ""
    if before is not None and before_id is not None:
        cursor_sql = (
            f"AND ({cursor_field} {comparator} ? OR ({cursor_field} = ? AND id {comparator} ?))"
        )
        params = [before, before, before_id]
    rows = q(
        f"""SELECT * FROM media WHERE trashed_ts IS NULL AND private=0 AND hidden=0 AND live_of IS NULL {clause} {cursor_sql}
            ORDER BY {base_order} LIMIT ?""",
        (*params, limit),
    )
    items = [media_dict(r) for r in rows]
    next_cursor = None
    if len(items) == limit:
        last = rows[-1]
        next_cursor = {"before": last[cursor_field], "before_id": last["id"]}
    return {"items": items, "next": next_cursor}


SEARCH_FIELDS = {"name", "ocr", "people", "albums"}


@router.get("/media/search")
def search_media(
    q_text: str = Query(alias="q", min_length=1, max_length=200),
    fields: str = Query("name,ocr,people,albums"),
    limit: int = Query(400, ge=1, le=1000),
):
    wanted = {f.strip() for f in fields.split(",") if f.strip()} & SEARCH_FIELDS
    if not wanted:
        wanted = set(SEARCH_FIELDS)
    like = f"%{q_text}%"
    clauses, params = [], []
    if "name" in wanted:
        clauses.append("m.name LIKE ?")
        params.append(like)
    if "ocr" in wanted:
        clauses.append("m.ocr_text LIKE ?")
        params.append(like)
    if "people" in wanted:
        clauses.append("p.name LIKE ?")
        params.append(like)
    if "albums" in wanted:
        clauses.append("al.name LIKE ?")
        params.append(like)
    rows = q(
        f"""SELECT DISTINCT m.* FROM media m
           LEFT JOIN faces f ON f.media_id = m.id
           LEFT JOIN people p ON p.id = f.person_id
           LEFT JOIN album_items ai ON ai.media_id = m.id
           LEFT JOIN albums al ON al.id = ai.album_id
           WHERE m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL
             AND ({" OR ".join(clauses)})
           ORDER BY m.created_ts DESC LIMIT ?""",
        (*params, limit),
    )
    return {"items": [media_dict(r) for r in rows], "query": q_text, "fields": sorted(wanted)}


@router.get("/media/summary")
def media_summary(level: str = Query("month")):
    fmt = "%Y" if level == "year" else "%Y-%m"
    periods = []
    rows = q(
        f"""SELECT strftime('{fmt}', created_ts, 'unixepoch', 'localtime') AS period, COUNT(*) AS n
            FROM media WHERE trashed_ts IS NULL AND private=0 AND hidden=0 AND live_of IS NULL GROUP BY period ORDER BY period DESC"""
    )
    for row in rows:
        covers = q(
            f"""SELECT id FROM media WHERE trashed_ts IS NULL AND private=0 AND hidden=0 AND live_of IS NULL
                AND strftime('{fmt}', created_ts, 'unixepoch', 'localtime') = ?
                ORDER BY created_ts DESC LIMIT 4""",
            (row["period"],),
        )
        periods.append({"period": row["period"], "count": row["n"], "covers": [c["id"] for c in covers]})
    return {"level": level, "periods": periods}


class FlagIn(BaseModel):
    on: bool


@router.get("/media/{media_id}")
def media_meta(media_id: int, request: Request):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    payload = media_dict(row)
    payload["albums"] = [
        {"id": a["id"], "name": a["name"]}
        for a in q(
            "SELECT al.id, al.name FROM album_items ai JOIN albums al ON al.id=ai.album_id WHERE ai.media_id=?",
            (media_id,),
        )
    ]
    return payload


@router.post("/media/{media_id}/favorite")
def set_favorite(media_id: int, body: FlagIn, request: Request):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    ex("UPDATE media SET favorite=? WHERE id=?", (1 if body.on else 0, media_id))
    return {"ok": True, "favorite": body.on}


@router.post("/media/{media_id}/viewed")
def mark_viewed(media_id: int, request: Request):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    ex("UPDATE media SET viewed_ts=? WHERE id=?", (now(), media_id))
    return {"ok": True}


@router.post("/media/{media_id}/hide")
def hide_media(media_id: int, request: Request):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    ex("UPDATE media SET hidden=1 WHERE id=?", (media_id,))
    from .. import vaultcrypt
    vaultcrypt.reconcile(media_id)
    return {"ok": True}


@router.post("/media/{media_id}/trash")
def trash_media(media_id: int, request: Request):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    if row["trashed_ts"] is not None:
        return {"ok": True}
    ex("UPDATE media SET trashed_ts=?, trash_reason='user' WHERE id=?", (now(), media_id))
    from .. import vaultcrypt
    vaultcrypt.reconcile(media_id)
    return {"ok": True}


@router.get("/media/{media_id}/thumb")
def media_thumb(media_id: int, request: Request, s: int = Query(384, ge=64, le=1024)):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    from .. import vaultcrypt
    if must_not_store(row):
        data = vaultcrypt.thumb_bytes(row, s)
        if data is None:
            raise HTTPException(404, detail="Thumbnail unavailable")
        return Response(data, media_type="image/webp", headers={"Cache-Control": NO_STORE})
    path = thumbs.ensure_thumb(media_id, row["rel_path"], row["kind"], s)
    if path is None:
        raise HTTPException(404, detail="Thumbnail unavailable")
    return revalidated_file(request, path, "image/webp" if path.endswith(".webp") else "image/jpeg")


def _iter_range(path: str, start: int, end: int) -> Iterator[bytes]:
    with open(path, "rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            block = handle.read(min(STREAM_CHUNK, remaining))
            if not block:
                break
            remaining -= len(block)
            yield block


def _parse_range(header: str, size: int) -> Optional[Tuple[int, int]]:
    match = RANGE_RE.match(header.strip())
    if match is None or size == 0:
        return None
    start_raw, end_raw = match.group(1), match.group(2)
    if start_raw == "" and end_raw == "":
        return None
    if start_raw == "":
        length = int(end_raw)
        if length == 0:
            return None
        start, end = max(0, size - length), size - 1
    else:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end


@router.get("/media/{media_id}/file")
def media_file(media_id: int, request: Request):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    from .. import vaultcrypt
    sealed = vaultcrypt.opener(row)
    guarded = must_not_store(row) or sealed is not None
    path = libraryfs.abs_path(row["rel_path"])
    if sealed is None and not os.path.isfile(path):
        raise HTTPException(404, detail="Original file missing on disk")
    size = sealed.size if sealed is not None else os.path.getsize(path)

    def reader(start: int, end: int) -> Iterator[bytes]:
        return sealed.iter_range(start, end) if sealed is not None else _iter_range(path, start, end)

    range_header = request.headers.get("range")
    if guarded:
        headers = {"Accept-Ranges": "bytes", "Cache-Control": NO_STORE}
    else:
        headers = revalidated_headers(file_tag(path), {"Accept-Ranges": "bytes"})
        if not range_header and tag_matches(request, headers["ETag"]):
            return Response(status_code=304, headers=headers)
    if range_header:
        parsed = _parse_range(range_header, size)
        if parsed is None:
            raise HTTPException(416, detail="Invalid range", headers={"Content-Range": f"bytes */{size}"})
        start, end = parsed
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(reader(start, end), status_code=206, media_type=row["mime"], headers=headers)
    headers["Content-Length"] = str(size)
    if request.method == "HEAD":
        return Response(media_type=row["mime"], headers=headers)
    return StreamingResponse(reader(0, size - 1), media_type=row["mime"], headers=headers)
