import base64
import hashlib
import hmac
import os
import time
from typing import Optional

from .db import setting_get, setting_set

TOKEN_TTL = 30 * 60
_SECRET = os.urandom(32)


def _secret() -> bytes:
    return _SECRET


def hash_passkey(passkey: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(passkey.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_passkey(passkey: str, stored: str) -> bool:
    try:
        salt_b64, digest_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
        want = base64.b64decode(digest_b64)
    except Exception:
        return False
    got = hashlib.scrypt(passkey.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(got, want)


def issue_token(scope: str) -> str:
    expires = int(time.time()) + TOKEN_TTL
    payload = f"{scope}|{expires}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def check_token(token: Optional[str], scope: str) -> bool:
    if not token:
        return False
    try:
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        got_scope, expires_raw, sig = payload.rsplit("|", 2)
    except Exception:
        return False
    if got_scope != scope and got_scope != "vault":
        return False
    body = f"{got_scope}|{expires_raw}"
    want = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, want):
        return False
    try:
        return int(expires_raw) >= int(time.time())
    except ValueError:
        return False


def vault_hash() -> Optional[str]:
    return setting_get("vault_passkey")


def set_vault(passkey: str) -> None:
    setting_set("vault_passkey", hash_passkey(passkey))
