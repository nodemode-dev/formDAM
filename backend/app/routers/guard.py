from fastapi import HTTPException, Request

from ..db import q, q1
from ..security import VAULT_HEADER
from ..vault import check_token


def token_of(request: Request) -> str:
    return request.headers.get(VAULT_HEADER, "")


def _any_token(request: Request, scope: str) -> bool:
    tokens = [token_of(request)]
    if request.url.path.endswith(("/thumb", "/file")):
        tokens += [value for name, value in request.cookies.items() if name == "dam_vt" or name.startswith("dam_at_")]
    return any(check_token(token, scope) for token in tokens if token)


def require_vault(request: Request) -> None:
    if not _any_token(request, "vault"):
        raise HTTPException(401, detail="Vault passkey required")


def can_view_private(media_id: int, request: Request) -> bool:
    if _any_token(request, "vault"):
        return True
    for row in q("SELECT album_id FROM album_items WHERE media_id=?", (media_id,)):
        if _any_token(request, f"album:{row['album_id']}"):
            return True
    return False


def ensure_visible(media_row, request: Request) -> None:
    if media_row is None:
        raise HTTPException(404, detail="No such item")
    keys = media_row.keys() if hasattr(media_row, "keys") else []
    if "live_of" in keys and media_row["live_of"]:
        parent = q1("SELECT * FROM media WHERE id=?", (media_row["live_of"],))
        if parent is not None and parent["private"] and not can_view_private(parent["id"], request):
            raise HTTPException(401, detail="This item is in a private album")
    if media_row["private"] and not can_view_private(media_row["id"], request):
        raise HTTPException(401, detail="This item is in a private album")
    chain = [media_row]
    if "live_of" in keys and media_row["live_of"]:
        linked = q1("SELECT * FROM media WHERE id=?", (media_row["live_of"],))
        if linked is not None:
            chain.append(linked)
    if any(link["hidden"] or link["trashed_ts"] is not None for link in chain) and not _any_token(request, "vault"):
        raise HTTPException(401, detail="Unlock Hidden & Recently Deleted to open this item")
