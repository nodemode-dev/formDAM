import base64
import glob
import hashlib
import io
import json
import os
import secrets
import shutil
import sys
import threading
import time
from typing import Any, Dict, Iterator, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .config import cache_dir, library_root
from .db import connect, ex, q, q1, reset_thread_conn, setting_get, setting_set

MAGIC = b"DAMV1\n"
HEADER_LEN = 16
CHUNK_LOG2 = 16
TAG_LEN = 16
SESSION_TTL = 30 * 60
SWEEP_EVERY = 15.0
VAULT_COOKIE = "dam_vt"
ALBUM_COOKIE = "dam_at_"
COOKIE_PATH = "/api/media"
WEBKIT_CACHE_IDS = ("ai.nodemode.dam", "ai.nodemode.damp")
VAULT_LABEL = b"dam-vault-sk"
SEAL_LABEL = b"dam-seal-v1"
META_LABEL = b"dam-meta-v1"

TABLES = """
CREATE TABLE IF NOT EXISTS vault_items(
  media_id INTEGER PRIMARY KEY,
  blob TEXT NOT NULL UNIQUE,
  sealed TEXT NOT NULL,
  home TEXT NOT NULL,
  home_rel TEXT NOT NULL,
  meta TEXT NOT NULL,
  sealed_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS vault_albums(
  key_id INTEGER PRIMARY KEY AUTOINCREMENT,
  album_id INTEGER NOT NULL,
  album_ts REAL NOT NULL,
  pub TEXT NOT NULL,
  wrap TEXT,
  prov TEXT,
  seal TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault_albums_album ON vault_albums(album_id);
"""

_op = threading.RLock()
_wake = threading.Event()
_session: Dict[str, Any] = {"vault": None, "albums": {}, "until": 0.0}
_state = {"sweeper": False}


class Locked(HTTPException):
    def __init__(self) -> None:
        super().__init__(401, detail="Unlock again to open this item")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.b64decode(text)


def _sk_raw(sk: X25519PrivateKey) -> bytes:
    return sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())


def _pk_raw(pk: X25519PublicKey) -> bytes:
    return pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _derive(shared: bytes, salt: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=SEAL_LABEL).derive(shared)


def _seal(data: bytes, pub: bytes) -> str:
    eph = X25519PrivateKey.generate()
    eph_pub = _pk_raw(eph.public_key())
    key = _derive(eph.exchange(X25519PublicKey.from_public_bytes(pub)), eph_pub + pub)
    nonce = os.urandom(12)
    return _b64(eph_pub + nonce + AESGCM(key).encrypt(nonce, data, SEAL_LABEL))


def _unseal(text: str, sk: X25519PrivateKey) -> bytes:
    raw = _unb64(text)
    eph_pub, nonce, body = raw[:32], raw[32:44], raw[44:]
    key = _derive(sk.exchange(X25519PublicKey.from_public_bytes(eph_pub)), eph_pub + _pk_raw(sk.public_key()))
    return AESGCM(key).decrypt(nonce, body, SEAL_LABEL)


def _kek(secret: str, salt: bytes) -> bytes:
    return hashlib.scrypt(secret.encode(), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)


def _wrap(raw: bytes, secret: str, label: bytes) -> str:
    salt, nonce = os.urandom(16), os.urandom(12)
    body = AESGCM(_kek(secret, salt)).encrypt(nonce, raw, label)
    return json.dumps({"salt": _b64(salt), "nonce": _b64(nonce), "body": _b64(body)})


def _unwrap(text: str, secret: str, label: bytes) -> Optional[bytes]:
    try:
        box = json.loads(text)
        return AESGCM(_kek(secret, _unb64(box["salt"]))).decrypt(_unb64(box["nonce"]), _unb64(box["body"]), label)
    except Exception:
        return None


def _aad(header: bytes, index: int, last: bool) -> bytes:
    return header + index.to_bytes(4, "big") + (b"\x01" if last else b"\x00")


def _part(dst: str) -> str:
    return f"{dst}.{secrets.token_hex(4)}.part"


def _encrypt_stream(source, dst: str, ck: bytes) -> None:
    chunk = 1 << CHUNK_LOG2
    prefix = os.urandom(8)
    header = MAGIC + bytes([1, CHUNK_LOG2]) + prefix
    aead = AESGCM(ck)
    part = _part(dst)
    with open(part, "wb") as out:
        out.write(header)
        current, index = source.read(chunk), 0
        while True:
            upcoming = source.read(chunk)
            out.write(aead.encrypt(prefix + index.to_bytes(4, "big"), current, _aad(header, index, not upcoming)))
            if not upcoming:
                break
            current, index = upcoming, index + 1
        out.flush()
        os.fsync(out.fileno())
    os.replace(part, dst)


def _encrypt_file(src: str, dst: str, ck: bytes) -> None:
    with open(src, "rb") as source:
        _encrypt_stream(source, dst, ck)


class Sealed:
    def __init__(self, path: str, ck: bytes) -> None:
        self.path, self.ck = path, ck
        with open(path, "rb") as handle:
            self.header = handle.read(HEADER_LEN)
        if len(self.header) != HEADER_LEN or self.header[:6] != MAGIC or self.header[6] != 1:
            raise ValueError("not a vault blob")
        self.chunk = 1 << self.header[7]
        full, rest = divmod(os.path.getsize(path) - HEADER_LEN, self.chunk + TAG_LEN)
        self.count = full + (1 if rest else 0)
        self.size = full * self.chunk + (rest - TAG_LEN if rest else 0)

    def iter_range(self, start: int, end: int) -> Iterator[bytes]:
        aead = AESGCM(self.ck)
        prefix = self.header[8:16]
        first, last = start // self.chunk, end // self.chunk
        with open(self.path, "rb") as handle:
            for index in range(first, last + 1):
                handle.seek(HEADER_LEN + index * (self.chunk + TAG_LEN))
                body = handle.read(self.chunk + TAG_LEN)
                nonce = prefix + index.to_bytes(4, "big")
                plain = aead.decrypt(nonce, body, _aad(self.header, index, index == self.count - 1))
                low = start - index * self.chunk if index == first else 0
                high = end - index * self.chunk + 1 if index == last else len(plain)
                yield plain[low:high]

    def read_all(self) -> bytes:
        return b"".join(self.iter_range(0, self.size - 1)) if self.size else b""

    def write_to(self, dst: str) -> None:
        part = _part(dst)
        with open(part, "wb") as out:
            if self.size:
                for block in self.iter_range(0, self.size - 1):
                    out.write(block)
            out.flush()
            os.fsync(out.fileno())
        os.replace(part, dst)


def ensure_keypair() -> None:
    with _op:
        if setting_get("vault_pub"):
            return
        sk = X25519PrivateKey.generate()
        setting_set("vault_sk_prov", _b64(_sk_raw(sk)))
        setting_set("vault_pub", _b64(_pk_raw(sk.public_key())))


def _vault_pub() -> bytes:
    ensure_keypair()
    return _unb64(setting_get("vault_pub"))


def _live() -> bool:
    return time.time() < _session["until"]


def _begin() -> None:
    if not _live():
        _session["vault"] = None
        _session["albums"] = {}
    _session["until"] = time.time() + SESSION_TTL


def _vault_sk() -> Optional[X25519PrivateKey]:
    if _live() and _session["vault"] is not None:
        return _session["vault"]
    prov = setting_get("vault_sk_prov")
    return X25519PrivateKey.from_private_bytes(_unb64(prov)) if prov else None


def unlock_vault(passkey: str) -> bool:
    with _op:
        ensure_keypair()
        wrapped, prov = setting_get("vault_sk_wrap"), setting_get("vault_sk_prov")
        raw: Optional[bytes] = None
        if wrapped:
            raw = _unwrap(wrapped, passkey, VAULT_LABEL)
        elif prov:
            raw = _unb64(prov)
            setting_set("vault_sk_wrap", _wrap(raw, passkey, VAULT_LABEL))
        if raw is None:
            return False
        ex("DELETE FROM settings WHERE key='vault_sk_prov'")
        _begin()
        _session["vault"] = X25519PrivateKey.from_private_bytes(raw)
    _wake.set()
    return True


def _album_label(album_id: int) -> bytes:
    return b"dam-album-sk:" + str(album_id).encode()


def _identity(album, passkey: Optional[str]):
    lookup = "SELECT * FROM vault_albums WHERE album_id=? AND album_ts=? ORDER BY key_id DESC LIMIT 1"
    found = q1(lookup, (album["id"], album["created_ts"]))
    if found is not None:
        return found
    sk = X25519PrivateKey.generate()
    raw = _sk_raw(sk)
    ex(
        "INSERT INTO vault_albums(album_id, album_ts, pub, wrap, prov, seal) VALUES(?,?,?,?,?,?)",
        (album["id"], album["created_ts"], _b64(_pk_raw(sk.public_key())),
         _wrap(raw, passkey, _album_label(album["id"])) if passkey else None,
         None if passkey else _b64(raw), _seal(raw, _vault_pub())),
    )
    return q1(lookup, (album["id"], album["created_ts"]))


def album_identity(album_id: int, passkey: Optional[str] = None) -> None:
    with _op:
        album = q1("SELECT id, created_ts FROM albums WHERE id=?", (album_id,))
        if album is not None:
            _identity(album, passkey)


def unlock_album(album_id: int, passkey: str) -> bool:
    with _op:
        album = q1("SELECT id, created_ts FROM albums WHERE id=?", (album_id,))
        if album is None:
            return False
        ident = _identity(album, passkey)
        label = _album_label(album_id)
        if ident["wrap"]:
            raw = _unwrap(ident["wrap"], passkey, label)
        else:
            raw = _unb64(ident["prov"])
            ex("UPDATE vault_albums SET wrap=?, prov=NULL WHERE key_id=?", (_wrap(raw, passkey, label), ident["key_id"]))
        if raw is None:
            return False
        _begin()
        _session["albums"][ident["key_id"]] = X25519PrivateKey.from_private_bytes(raw)
    _wake.set()
    return True


def _album_sk(key_id: int) -> Optional[X25519PrivateKey]:
    if _live() and key_id in _session["albums"]:
        return _session["albums"][key_id]
    ident = q1("SELECT * FROM vault_albums WHERE key_id=?", (key_id,))
    if ident is None:
        return None
    if ident["prov"]:
        return X25519PrivateKey.from_private_bytes(_unb64(ident["prov"]))
    vault = _vault_sk()
    if vault is None:
        return None
    try:
        return X25519PrivateKey.from_private_bytes(_unseal(ident["seal"], vault))
    except Exception:
        return None


def _sealed_flag(row) -> bool:
    return bool(row["hidden"]) or row["trashed_ts"] is not None


def protected(row) -> bool:
    if _sealed_flag(row) or row["private"]:
        return True
    if row["live_of"]:
        parent = q1("SELECT hidden, trashed_ts, private FROM media WHERE id=?", (row["live_of"],))
        return parent is not None and (_sealed_flag(parent) or bool(parent["private"]))
    return False


def home_for(row) -> Optional[str]:
    chain = [row]
    if row["live_of"]:
        parent = q1("SELECT * FROM media WHERE id=?", (row["live_of"],))
        if parent is not None:
            chain.append(parent)
    if any(_sealed_flag(link) for link in chain):
        return "v"
    owner = next((link for link in reversed(chain) if link["private"]), None)
    if owner is None:
        return None
    for album in q(
        """SELECT a.id, a.created_ts, a.passkey_hash FROM album_items ai JOIN albums a ON a.id=ai.album_id
           WHERE ai.media_id=? AND a.is_private=1 ORDER BY a.id""",
        (owner["id"],),
    ):
        if album["passkey_hash"]:
            return f"a:{_identity(album, None)['key_id']}"
    return "v"


def _home_pub(home: str) -> bytes:
    if home == "v":
        return _vault_pub()
    return _unb64(q1("SELECT pub FROM vault_albums WHERE key_id=?", (int(home[2:]),))["pub"])


def _home_sk(home: str) -> Optional[X25519PrivateKey]:
    return _vault_sk() if home == "v" else _album_sk(int(home[2:]))


def _vault_dir() -> str:
    folder = os.path.join(library_root(), "vault")
    os.makedirs(folder, exist_ok=True)
    return folder


def _blob(name: str, suffix: str = "") -> str:
    return os.path.join(_vault_dir(), name + suffix)


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _drop(name: str) -> None:
    for path in glob.glob(os.path.join(glob.escape(_vault_dir()), name + "*")):
        _unlink(path)


def _scrub(media_id: int) -> None:
    folder = os.path.join(cache_dir(), "thumbs")
    for path in glob.glob(os.path.join(glob.escape(folder), f"{media_id}_*")):
        _unlink(path)
    for sub in ("render", "effects", "share"):
        for path in glob.glob(os.path.join(glob.escape(os.path.join(cache_dir(), sub)), f"{media_id}_*")):
            _unlink(path)
    faces = os.path.join(cache_dir(), "faces")
    for face in q("SELECT id FROM faces WHERE media_id=?", (media_id,)):
        _unlink(os.path.join(faces, f"{face['id']}.jpg"))


def _item(media_id: int):
    return q1("SELECT * FROM vault_items WHERE media_id=?", (media_id,))


def _flag_webcache() -> None:
    try:
        with open(os.path.join(library_root(), ".webcache-dirty"), "w"):
            pass
    except OSError:
        pass


def _protect(row, home: str) -> None:
    from .services import libraryfs, thumbs

    media_id = row["id"]
    if "referenced" in row.keys() and row["referenced"]:
        row = libraryfs.consolidate(media_id)
        if row is None:
            return
    src = libraryfs.abs_path(row["rel_path"])
    if not os.path.isfile(src):
        return
    ck, blob = os.urandom(32), secrets.token_hex(16)
    for size in thumbs.SIZES:
        plain = thumbs.thumb_path(media_id, size)
        if os.path.isfile(plain):
            _encrypt_file(plain, _blob(blob, f".t{size}"), ck)
    if not os.path.isfile(_blob(blob, ".t384")):
        made = thumbs.ensure_thumb(media_id, row["rel_path"], row["kind"], 384)
        if made and os.path.isfile(made):
            _encrypt_file(made, _blob(blob, ".p384" if "_ph." in made else ".t384"), ck)
    _encrypt_file(src, _blob(blob), ck)
    meta = json.dumps({"ocr": row["ocr_text"], "face_state": row["face_state"]}).encode()
    nonce = os.urandom(12)
    ex(
        "INSERT INTO vault_items(media_id, blob, sealed, home, home_rel, meta, sealed_ts) VALUES(?,?,?,?,?,?,?)",
        (media_id, blob, _seal(ck, _home_pub(home)), home, row["rel_path"],
         _b64(nonce + AESGCM(ck).encrypt(nonce, meta, META_LABEL)), time.time()),
    )
    ex("UPDATE media SET ocr_text='', face_state=CASE WHEN face_state=0 THEN 2 ELSE face_state END WHERE id=?", (media_id,))
    _unlink(src)
    _scrub(media_id)
    _flag_webcache()


def _open_ck(item) -> bytes:
    sk = _home_sk(item["home"])
    if sk is None:
        raise Locked()
    try:
        return _unseal(item["sealed"], sk)
    except Exception:
        raise Locked() from None


def _unprotect(row, item) -> None:
    from .services import libraryfs, thumbs

    media_id = row["id"]
    ck = _open_ck(item)
    rel = item["home_rel"]
    dest = libraryfs.abs_path(rel)
    if os.path.exists(dest) or q1("SELECT id FROM media WHERE rel_path=? AND id<>?", (rel, media_id)):
        dest = libraryfs._dest_for(row["created_ts"], os.path.basename(rel))
        rel = os.path.relpath(dest, libraryfs.abs_path(""))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    Sealed(_blob(item["blob"]), ck).write_to(dest)
    for size in thumbs.SIZES:
        path = _blob(item["blob"], f".t{size}")
        if os.path.isfile(path):
            Sealed(path, ck).write_to(thumbs.thumb_path(media_id, size))
    raw = _unb64(item["meta"])
    meta = json.loads(AESGCM(ck).decrypt(raw[:12], raw[12:], META_LABEL))
    ex(
        "UPDATE media SET rel_path=?, ocr_text=?, face_state=? WHERE id=?",
        (rel, meta.get("ocr"), meta.get("face_state", 0), media_id),
    )
    ex("DELETE FROM vault_items WHERE media_id=?", (media_id,))
    _drop(item["blob"])


def _reseal(item, home: str) -> None:
    ck = _open_ck(item)
    ex("UPDATE vault_items SET sealed=?, home=? WHERE media_id=?", (_seal(ck, _home_pub(home)), home, item["media_id"]))


def _settle(row) -> bool:
    try:
        home = home_for(row)
        item = _item(row["id"])
        if home is not None and item is None:
            _protect(row, home)
        elif home is None and item is not None:
            _unprotect(row, item)
        elif item is not None and item["home"] != home:
            _reseal(item, home)
    except Locked:
        return False
    except Exception as exc:
        print(f"vault: item {row['id']} not settled: {exc}", flush=True)
        return False
    return True


def reconcile(media_id: int) -> bool:
    with _op:
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        if row is None:
            return True
        ok = _settle(row)
        if row["live_video_id"]:
            companion = q1("SELECT * FROM media WHERE id=?", (row["live_video_id"],))
            if companion is not None:
                ok = _settle(companion) and ok
    return ok


def purge(media_id: int) -> None:
    with _op:
        item = _item(media_id)
        if item is not None:
            _drop(item["blob"])
            ex("DELETE FROM vault_items WHERE media_id=?", (media_id,))
        _scrub(media_id)
        from .services.extedit import edits_dir, work_dir

        for folder in (edits_dir(), work_dir()):
            for path in glob.glob(os.path.join(glob.escape(folder), f"{media_id}-*")):
                _unlink(path)


def is_vaulted(media_id: int) -> bool:
    return _item(media_id) is not None


def opener(row) -> Optional[Sealed]:
    item = _item(row["id"])
    if item is None and protected(row):
        reconcile(row["id"])
        item = _item(row["id"])
    if item is None:
        return None
    ck = _open_ck(item)
    try:
        return Sealed(_blob(item["blob"]), ck)
    except OSError:
        return None


def thumb_bytes(row, requested: int) -> Optional[bytes]:
    from PIL import Image, ImageOps

    from .services import thumbs

    item = _item(row["id"])
    if item is None and protected(row):
        reconcile(row["id"])
        item = _item(row["id"])
    if item is None:
        return None
    ck = _open_ck(item)
    size = thumbs._bucket(requested)
    exact = _blob(item["blob"], f".t{size}")
    try:
        if os.path.isfile(exact):
            return Sealed(exact, ck).read_all()
        if row["kind"] == "image":
            with Image.open(io.BytesIO(Sealed(_blob(item["blob"]), ck).read_all())) as img:
                img.draft("RGB", (size * 2, size * 2))
                frame = ImageOps.exif_transpose(img).convert("RGB")
            frame.thumbnail((size, size), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            frame.save(out, "WEBP", quality=80, method=4)
            _encrypt_stream(io.BytesIO(out.getvalue()), exact, ck)
            return out.getvalue()
    except Exception:
        pass
    for other in sorted(thumbs.SIZES, key=lambda value: abs(value - size)):
        for tag in (".t", ".p"):
            path = _blob(item["blob"], f"{tag}{other}")
            if os.path.isfile(path):
                try:
                    return Sealed(path, ck).read_all()
                except Exception:
                    return None
    return None


def token_response(token: str, cookie: str) -> JSONResponse:
    response = JSONResponse({"token": token})
    response.set_cookie(cookie, token, httponly=True, samesite="strict", path=COOKIE_PATH)
    return response


def _purge_webcache() -> None:
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return
    root = library_root()
    dirty, done = os.path.join(root, ".webcache-dirty"), os.path.join(root, ".webcache-v1")
    if os.path.exists(done) and not os.path.exists(dirty):
        return
    for ident in WEBKIT_CACHE_IDS:
        shutil.rmtree(os.path.join(os.path.expanduser("~"), "Library", "Caches", ident, "WebKit"), ignore_errors=True)
    _unlink(dirty)
    with open(done, "w"):
        pass


def _scrub_vaulted() -> None:
    vaulted = {row["media_id"] for row in q("SELECT media_id FROM vault_items")}
    if not vaulted:
        return
    folder = os.path.join(cache_dir(), "thumbs")
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    for name in names:
        head = name.split("_", 1)[0]
        if head.isdigit() and int(head) in vaulted:
            _unlink(os.path.join(folder, name))
    faces = os.path.join(cache_dir(), "faces")
    for face in q("SELECT f.id FROM faces f JOIN vault_items v ON v.media_id=f.media_id"):
        _unlink(os.path.join(faces, f"{face['id']}.jpg"))


def _forget_orphans() -> None:
    ex(
        """DELETE FROM vault_albums
           WHERE key_id NOT IN (SELECT CAST(substr(home, 3) AS INTEGER) FROM vault_items WHERE home LIKE 'a:%')
             AND NOT EXISTS (SELECT 1 FROM albums a WHERE a.id=vault_albums.album_id AND a.created_ts=vault_albums.album_ts)"""
    )


def sweep() -> int:
    reset_thread_conn()
    root = library_root()
    if q1("SELECT name FROM sqlite_master WHERE type='table' AND name='vault_items'") is None:
        return 0
    ids = [row["id"] for row in q(
        """SELECT m.id FROM media m LEFT JOIN vault_items v ON v.media_id=m.id
           WHERE v.media_id IS NULL AND (m.hidden=1 OR m.private=1 OR m.trashed_ts IS NOT NULL
             OR m.live_of IN (SELECT id FROM media WHERE hidden=1 OR private=1 OR trashed_ts IS NOT NULL))"""
    )]
    if _live() or setting_get("vault_sk_prov"):
        ids += [row["media_id"] for row in q("SELECT media_id FROM vault_items")]
    for media_id in ids:
        if library_root() != root:
            return 0
        reconcile(media_id)
    with _op:
        _scrub_vaulted()
        _forget_orphans()
    return len(ids)


def _sweep_loop() -> None:
    while True:
        _wake.wait(SWEEP_EVERY)
        _wake.clear()
        try:
            sweep()
        except Exception as exc:
            print(f"vault: sweep failed: {exc}", flush=True)
        finally:
            reset_thread_conn()


def startup() -> None:
    connect().executescript(TABLES)
    ensure_keypair()
    _session.update(vault=None, albums={}, until=0.0)
    for leftover in glob.glob(os.path.join(glob.escape(_vault_dir()), "*.part")):
        _unlink(leftover)
    _purge_webcache()
    if not _state["sweeper"]:
        _state["sweeper"] = True
        threading.Thread(target=_sweep_loop, name="vault-sweep", daemon=True).start()
    _wake.set()
