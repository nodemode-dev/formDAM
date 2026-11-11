import os
from typing import Dict, Optional

from fastapi import Request
from fastapi.responses import FileResponse, Response

REVALIDATE = "private, no-cache"
NO_STORE = "no-store"


def must_not_store(row) -> bool:
    from .. import vaultcrypt

    return vaultcrypt.protected(row) or vaultcrypt.is_vaulted(row["id"])


def file_tag(path: str) -> str:
    stat = os.stat(path)
    return f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'


def tag_matches(request: Request, tag: str) -> bool:
    return tag in [part.strip() for part in request.headers.get("if-none-match", "").split(",")]


def revalidated_headers(tag: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    return {**(extra or {}), "Cache-Control": REVALIDATE, "ETag": tag}


def revalidated_file(request: Request, path: str, media_type: str) -> Response:
    tag = file_tag(path)
    headers = revalidated_headers(tag)
    if tag_matches(request, tag):
        return Response(status_code=304, headers=headers)
    return FileResponse(path, media_type=media_type, headers=headers)
