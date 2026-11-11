import os
import sys
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..config import trash_retention_days
from ..db import ex, media_dict, q, q1
from ..security import shell_allowed, window_allowed
from ..services import libraryfs
from ..vault import issue_token, set_vault, vault_hash, verify_passkey
from .guard import require_vault

router = APIRouter()


class PasskeyIn(BaseModel):
    passkey: str = Field(min_length=4, max_length=128)


@router.get("/vault/status")
def vault_status():
    return {"configured": vault_hash() is not None}


@router.post("/vault/setup")
def vault_setup(body: PasskeyIn):
    if vault_hash() is not None:
        raise HTTPException(409, detail="Vault passkey already set")
    set_vault(body.passkey)
    from .. import vaultcrypt
    vaultcrypt.unlock_vault(body.passkey)
    return vaultcrypt.token_response(issue_token("vault"), vaultcrypt.VAULT_COOKIE)


@router.post("/vault/unlock")
def vault_unlock(body: PasskeyIn):
    stored = vault_hash()
    if stored is None:
        raise HTTPException(409, detail="Vault passkey not set yet")
    if not verify_passkey(body.passkey, stored):
        raise HTTPException(401, detail="Wrong passkey")
    from .. import vaultcrypt
    if not vaultcrypt.unlock_vault(body.passkey):
        raise HTTPException(500, detail="The vault key could not be opened with this passkey")
    return vaultcrypt.token_response(issue_token("vault"), vaultcrypt.VAULT_COOKIE)


@router.post("/vault/lock")
def vault_lock():
    from .. import vaultcrypt
    response = JSONResponse({"ok": True})
    response.delete_cookie(vaultcrypt.VAULT_COOKIE, path=vaultcrypt.COOKIE_PATH, httponly=True, samesite="strict")
    return response


KEYCHAIN_SERVICE = "ai.nodemode.dam.vault"


def device_labels() -> dict:
    if sys.platform == "darwin":
        return {"method": "Touch ID", "store": "the macOS Keychain"}
    if os.name == "nt":
        return {"method": "Windows Hello", "store": "Windows Credential Manager"}
    return {"method": "system sign-in", "store": "the system keyring"}


def _method_cap() -> str:
    method = device_labels()["method"]
    return method[:1].upper() + method[1:]


SHELL = {"attached": False, "bio": False, "stored": False}
PENDING: dict = {}


class ShellHello(BaseModel):
    bio: bool = False
    stored: bool = False


class BioResult(BaseModel):
    nonce: str
    ok: bool
    passkey: str | None = None
    stored: bool | None = None


def _shell_only(request: Request) -> None:
    if not shell_allowed(request):
        raise HTTPException(403, detail="Only the formDAM desktop shell may call this")


@router.post("/internal/shell/hello")
def shell_hello(body: ShellHello, request: Request):
    _shell_only(request)
    SHELL.update(attached=True, bio=body.bio, stored=body.stored)
    return {"ok": True}


@router.get("/internal/bio/pending/{nonce}")
def bio_pending(nonce: str, request: Request):
    _shell_only(request)
    entry = PENDING.get(nonce)
    if entry is None:
        raise HTTPException(404, detail="No such request")
    return {"passkey": entry.get("passkey")}


@router.post("/internal/bio/result")
def bio_result(body: BioResult, request: Request):
    _shell_only(request)
    entry = PENDING.get(body.nonce)
    if entry is None:
        raise HTTPException(404, detail="No such request")
    entry["ok"] = body.ok
    entry["result_passkey"] = body.passkey
    if body.stored is not None:
        SHELL["stored"] = body.stored
    entry["event"].set()
    return {"ok": True}


def _ctrl_roundtrip(kind: str, passkey: str | None = None, timeout: float = 40.0) -> dict:
    if not SHELL["attached"]:
        raise HTTPException(501, detail=f"The desktop shell is not attached; {device_labels()['method']} needs the formDAM desktop app.")
    nonce = os.urandom(12).hex()
    entry: dict = {"event": __import__("threading").Event(), "passkey": passkey}
    PENDING[nonce] = entry
    print(f"FORMDAM-CTRL {kind} {nonce}", flush=True)
    finished = entry["event"].wait(timeout)
    PENDING.pop(nonce, None)
    if not finished:
        raise HTTPException(504, detail=f"{_method_cap()} timed out")
    return entry


@router.get("/vault/keychain/status")
def keychain_status():
    return {"available": SHELL["attached"] and SHELL["bio"], "stored": SHELL["stored"]}


@router.get("/vault/device")
def device_unlock_labels():
    return device_labels()


@router.post("/vault/keychain/enable")
def keychain_enable(body: PasskeyIn):
    stored = vault_hash()
    if stored is None or not verify_passkey(body.passkey, stored):
        raise HTTPException(401, detail="Wrong passkey")
    entry = _ctrl_roundtrip("KCSTORE", passkey=body.passkey)
    if not entry.get("ok"):
        raise HTTPException(500, detail=f"The shell could not save the passkey to {device_labels()['store']}")
    return {"ok": True}


@router.post("/vault/bio/unlock")
def bio_unlock(request: Request):
    if not (window_allowed(request) or shell_allowed(request)):
        raise HTTPException(403, detail="Device unlock is only offered in the formDAM window")
    stored_hash = vault_hash()
    if stored_hash is None:
        raise HTTPException(400, detail="No vault passkey is set yet")
    entry = _ctrl_roundtrip("BIOUNLOCK")
    if not entry.get("ok") or not entry.get("result_passkey"):
        raise HTTPException(401, detail=f"{_method_cap()} was cancelled or failed")
    if not verify_passkey(entry["result_passkey"], stored_hash):
        raise HTTPException(401, detail=f"The passkey saved in {device_labels()['store']} no longer matches the vault passkey")
    from .. import vaultcrypt
    if not vaultcrypt.unlock_vault(entry["result_passkey"]):
        raise HTTPException(500, detail="The vault key could not be opened with this passkey")
    return vaultcrypt.token_response(issue_token("vault"), vaultcrypt.VAULT_COOKIE)


@router.get("/hidden")
def list_hidden(request: Request):
    require_vault(request)
    rows = q("SELECT * FROM media WHERE hidden=1 AND trashed_ts IS NULL ORDER BY created_ts DESC")
    return {"items": [media_dict(r) for r in rows]}


@router.post("/hidden/{media_id}/unhide")
def unhide(media_id: int, request: Request):
    require_vault(request)
    row = q1("SELECT id FROM media WHERE id=? AND hidden=1", (media_id,))
    if row is None:
        raise HTTPException(404, detail="Not hidden")
    ex("UPDATE media SET hidden=0 WHERE id=?", (media_id,))
    from .. import vaultcrypt
    if not vaultcrypt.reconcile(media_id):
        ex("UPDATE media SET hidden=1 WHERE id=?", (media_id,))
        raise HTTPException(401, detail="This item could not be decrypted. Unlock again and retry.")
    return {"ok": True}


@router.get("/trash")
def list_trash(request: Request):
    require_vault(request)
    rows = q("SELECT * FROM media WHERE trashed_ts IS NOT NULL ORDER BY trashed_ts DESC")
    retention = trash_retention_days()
    items = []
    for row in rows:
        item = media_dict(row)
        days_left = max(0, retention - int((time.time() - row["trashed_ts"]) / 86400))
        item["days_left"] = days_left
        items.append(item)
    return {"items": items, "retention_days": retention}


@router.post("/trash/{media_id}/restore")
def restore(media_id: int, request: Request):
    require_vault(request)
    row = q1("SELECT * FROM media WHERE id=? AND trashed_ts IS NOT NULL", (media_id,))
    if row is None:
        raise HTTPException(404, detail="Not in the trash")
    ex("UPDATE media SET trashed_ts=NULL, trash_reason=NULL WHERE id=?", (media_id,))
    from .. import vaultcrypt
    if not vaultcrypt.reconcile(media_id):
        ex("UPDATE media SET trashed_ts=?, trash_reason=? WHERE id=?", (row["trashed_ts"], row["trash_reason"], media_id))
        raise HTTPException(401, detail="This item could not be decrypted. Unlock again and retry.")
    return {"ok": True}


def _purge_row(row) -> None:
    from .. import vaultcrypt
    vaultcrypt.purge(row["id"])
    keys = row.keys() if hasattr(row, "keys") else []
    companion = q1("SELECT * FROM media WHERE live_of=?", (row["id"],)) if "live_of" in keys else None
    path = libraryfs.abs_path(row["rel_path"])
    if os.path.isfile(path) and not ("referenced" in keys and row["referenced"]):
        os.unlink(path)
    ex("DELETE FROM faces WHERE media_id=?", (row["id"],))
    ex("DELETE FROM album_items WHERE media_id=?", (row["id"],))
    ex("DELETE FROM media_keywords WHERE media_id=?", (row["id"],))
    ex("DELETE FROM dup_members WHERE media_id=?", (row["id"],))
    ex("DELETE FROM media WHERE id=?", (row["id"],))
    if "live_of" in keys and row["live_of"]:
        ex("UPDATE media SET live_video_id=NULL WHERE id=?", (row["live_of"],))
    if companion is not None:
        _purge_row(companion)


@router.delete("/trash/{media_id}")
def delete_forever(media_id: int, request: Request):
    require_vault(request)
    row = q1("SELECT * FROM media WHERE id=? AND trashed_ts IS NOT NULL", (media_id,))
    if row is None:
        raise HTTPException(404, detail="Not in the trash")
    _purge_row(row)
    return {"ok": True}


@router.post("/trash/empty")
def empty_trash(request: Request):
    require_vault(request)
    rows = q("SELECT * FROM media WHERE trashed_ts IS NOT NULL")
    for row in rows:
        _purge_row(row)
    return {"deleted": len(rows)}


def purge_expired() -> int:
    cutoff = time.time() - trash_retention_days() * 86400
    rows = q("SELECT * FROM media WHERE trashed_ts IS NOT NULL AND trashed_ts < ?", (cutoff,))
    for row in rows:
        _purge_row(row)
    return len(rows)
