import hashlib
import io
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from ..config import cache_dir
from ..db import q1
from ..services import decode, editsvc, libraryfs
from .guard import ensure_visible
from .revalidate import NO_STORE, file_tag, must_not_store, revalidated_file, revalidated_headers

router = APIRouter()
WIDTHS = (640, 1280, 2048, 3072, 4096)


def _bucket(w: int) -> int:
    for size in WIDTHS:
        if w <= size:
            return size
    return WIDTHS[-1]


def render_folder() -> str:
    folder = os.path.join(cache_dir(), "render")
    os.makedirs(folder, exist_ok=True)
    return folder


def clear_cached(media_id: int) -> None:
    folder = render_folder()
    prefix = f"{media_id}_"
    for name in os.listdir(folder):
        if name.startswith(prefix):
            try:
                os.unlink(os.path.join(folder, name))
            except OSError:
                pass


def source_of(row):
    from .. import vaultcrypt

    sealed = vaultcrypt.opener(row)
    if sealed is not None:
        return b"".join(sealed.iter_range(0, sealed.size - 1)), True
    path = libraryfs.abs_path(row["rel_path"])
    if not os.path.isfile(path):
        return None, False
    return path, vaultcrypt.protected(row)


def render_image(row, width: int):
    src, protected = source_of(row)
    if src is None:
        return None, protected
    img = editsvc.render_still(row["id"], src, width)
    if img is None:
        img = decode.open_image(src, row["name"], max_long=width)
    return img, protected


@router.get("/media/{media_id}/render")
def render(media_id: int, request: Request, w: int = Query(2048, ge=64, le=8192)):
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    ensure_visible(row, request)
    if row["kind"] != "image":
        raise HTTPException(415, detail="Only stills render; videos stream from /file")
    width = _bucket(w)
    stamp = hashlib.sha1(f"{row['edit_json'] or ''}|{row['edited_ts'] or 0}".encode()).hexdigest()[:12]
    cached = os.path.join(render_folder(), f"{media_id}_{width}_{stamp}.webp")
    if not must_not_store(row) and os.path.isfile(cached):
        return revalidated_file(request, cached, "image/webp")
    img, protected = render_image(row, width)
    if img is None:
        raise HTTPException(404, detail="This file could not be decoded")
    buf = io.BytesIO()
    img.convert("RGBA" if img.mode == "RGBA" else "RGB").save(buf, "WEBP", quality=88, method=4)
    data = buf.getvalue()
    if protected or must_not_store(row):
        return Response(data, media_type="image/webp", headers={"Cache-Control": NO_STORE})
    tmp = cached + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, cached)
    return Response(data, media_type="image/webp", headers=revalidated_headers(file_tag(cached)))
