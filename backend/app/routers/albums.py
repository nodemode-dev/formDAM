from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import ex, media_dict, now, q, q1
from ..vault import check_token, hash_passkey, issue_token, vault_hash, verify_passkey
from .guard import token_of

router = APIRouter()


class AlbumIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_private: bool = False
    passkey: Optional[str] = Field(None, min_length=4, max_length=128)


class ItemsIn(BaseModel):
    media_ids: List[int]


class UnlockIn(BaseModel):
    passkey: str


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _album_or_404(album_id: int):
    row = q1("SELECT * FROM albums WHERE id=?", (album_id,))
    if row is None:
        raise HTTPException(404, detail="No such album")
    return row


def _require_album_access(album, request: Request) -> None:
    if not album["is_private"]:
        return
    if not check_token(token_of(request), f"album:{album['id']}"):
        raise HTTPException(401, detail="This album is private. Unlock it with its passkey.")


def _album_payload(album, count: int):
    keys = album.keys()
    rules = album["rules_json"] if "rules_json" in keys else None
    payload = {
        "id": album["id"], "name": album["name"], "is_private": bool(album["is_private"]),
        "count": count, "cover_media_id": album["cover_media_id"], "created_ts": album["created_ts"],
        "folder_id": album["folder_id"] if "folder_id" in keys else None,
        "is_smart": bool(rules),
    }
    if rules:
        from ..services import query
        spec = query.parse_spec(rules)
        payload["rules"] = spec
        payload["count"] = query.count(spec)
        top = query.ids(spec, limit=1)
        payload["cover_media_id"] = top[0] if top else None
    return payload


@router.get("/albums")
def list_albums():
    albums = []
    for row in q("SELECT * FROM albums ORDER BY position, id"):
        count = q1("SELECT COUNT(*) AS n FROM album_items WHERE album_id=?", (row["id"],))["n"]
        albums.append(_album_payload(row, count))
    return {"albums": albums}


@router.post("/albums", status_code=201)
def create_album(body: AlbumIn):
    passkey_hash = None
    if body.is_private:
        if body.passkey:
            passkey_hash = hash_passkey(body.passkey)
        elif vault_hash() is None:
            raise HTTPException(422, detail="Private albums need a passkey (or set the vault passkey first)")
    album_id = ex(
        "INSERT INTO albums(name, created_ts, is_private, passkey_hash) VALUES(?,?,?,?)",
        (body.name.strip(), now(), 1 if body.is_private else 0, passkey_hash),
    )
    if passkey_hash:
        from .. import vaultcrypt
        vaultcrypt.album_identity(album_id, body.passkey)
    return _album_payload(q1("SELECT * FROM albums WHERE id=?", (album_id,)), 0)


@router.post("/albums/{album_id}/unlock")
def unlock_album(album_id: int, body: UnlockIn):
    album = _album_or_404(album_id)
    if not album["is_private"]:
        raise HTTPException(422, detail="Album is not private")
    stored = album["passkey_hash"] or vault_hash()
    if stored is None or not verify_passkey(body.passkey, stored):
        raise HTTPException(401, detail="Wrong passkey")
    from .. import vaultcrypt
    if album["passkey_hash"]:
        opened = vaultcrypt.unlock_album(album_id, body.passkey)
    else:
        opened = vaultcrypt.unlock_vault(body.passkey)
    if not opened:
        raise HTTPException(500, detail="The album key could not be opened with this passkey")
    return vaultcrypt.token_response(issue_token(f"album:{album_id}"), f"{vaultcrypt.ALBUM_COOKIE}{album_id}")


@router.get("/albums/{album_id}")
def album_detail(album_id: int, request: Request):
    album = _album_or_404(album_id)
    _require_album_access(album, request)
    if album["rules_json"]:
        from ..services import query
        spec = query.parse_spec(album["rules_json"])
        rows = query.page(spec, limit=5000)["rows"]
        payload = _album_payload(album, len(rows))
        payload["items"] = [{k: v for k, v in media_dict(r).items() if k != "_sortv"} for r in rows]
        return payload
    rows = q(
        """SELECT m.* FROM album_items ai JOIN media m ON m.id=ai.media_id
           WHERE ai.album_id=? AND m.trashed_ts IS NULL AND m.hidden=0 ORDER BY ai.position, ai.added_ts""",
        (album_id,),
    )
    payload = _album_payload(album, len(rows))
    payload["items"] = [media_dict(r) for r in rows]
    return payload


def _refresh_private_flag(media_id: int) -> None:
    row = q1(
        """SELECT COUNT(*) AS n FROM album_items ai JOIN albums a ON a.id=ai.album_id
           WHERE ai.media_id=? AND a.is_private=1""",
        (media_id,),
    )
    ex("UPDATE media SET private=? WHERE id=?", (1 if row["n"] else 0, media_id))
    from .. import vaultcrypt
    vaultcrypt.reconcile(media_id)


@router.post("/albums/{album_id}/items")
def add_items(album_id: int, body: ItemsIn, request: Request):
    album = _album_or_404(album_id)
    _require_album_access(album, request)
    if album["rules_json"]:
        raise HTTPException(409, detail="Smart albums fill themselves from their rules")
    added = 0
    for media_id in body.media_ids:
        if q1("SELECT id FROM media WHERE id=? AND trashed_ts IS NULL", (media_id,)) is None:
            continue
        ex(
            "INSERT OR IGNORE INTO album_items(album_id, media_id, position, added_ts) VALUES(?,?,?,?)",
            (album_id, media_id, 0, now()),
        )
        _refresh_private_flag(media_id)
        added += 1
    if album["cover_media_id"] is None and body.media_ids:
        ex("UPDATE albums SET cover_media_id=? WHERE id=?", (body.media_ids[0], album_id))
    return {"added": added}


@router.delete("/albums/{album_id}/items")
def remove_items(album_id: int, body: ItemsIn, request: Request):
    album = _album_or_404(album_id)
    _require_album_access(album, request)
    for media_id in body.media_ids:
        ex("DELETE FROM album_items WHERE album_id=? AND media_id=?", (album_id, media_id))
        _refresh_private_flag(media_id)
    return {"ok": True}


@router.patch("/albums/{album_id}")
def rename_album(album_id: int, body: RenameIn, request: Request):
    album = _album_or_404(album_id)
    _require_album_access(album, request)
    ex("UPDATE albums SET name=? WHERE id=?", (body.name.strip(), album_id))
    return {"ok": True}


class OrderIn(BaseModel):
    media_ids: List[int]


@router.put("/albums/{album_id}/order")
def set_order(album_id: int, body: OrderIn, request: Request):
    album = q1("SELECT * FROM albums WHERE id=?", (album_id,))
    if album is None:
        raise HTTPException(404, detail="No such album")
    _require_album_access(album, request)
    for position, mid in enumerate(body.media_ids):
        ex("UPDATE album_items SET position=? WHERE album_id=? AND media_id=?", (position, album_id, mid))
    return {"ok": True}


@router.delete("/albums/{album_id}")
def delete_album(album_id: int, request: Request):
    album = _album_or_404(album_id)
    _require_album_access(album, request)
    members = [r["media_id"] for r in q("SELECT media_id FROM album_items WHERE album_id=?", (album_id,))]
    ex("DELETE FROM album_items WHERE album_id=?", (album_id,))
    ex("DELETE FROM albums WHERE id=?", (album_id,))
    for media_id in members:
        _refresh_private_flag(media_id)
    return {"ok": True}
