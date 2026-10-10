import base64
import hashlib
import hmac
import io
import os
import secrets
import socket
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

from ..config import cache_dir
from ..db import ex, q, q1, setting_get, setting_set
from ..vault import hash_passkey, verify_passkey
from . import thumbs

DEFAULT_PORT = 8790
COOKIE_TTL = 7 * 24 * 3600
MAX_TEXT = 1000
MAX_NAME = 60
SHAREABLE = "m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL"
IDS_TTL_S = 5.0
_ids_cache: Dict[Any, Any] = {}


def settings() -> Dict[str, Any]:
    try:
        port = int(setting_get("share_port") or DEFAULT_PORT)
    except ValueError:
        port = DEFAULT_PORT
    return {"enabled": setting_get("share_enabled") == "1", "port": port, "name": setting_get("share_name") or "DAM"}


def save_settings(enabled: Optional[bool] = None, port: Optional[int] = None, name: Optional[str] = None) -> Dict[str, Any]:
    if enabled is not None:
        setting_set("share_enabled", "1" if enabled else "0")
    if port is not None:
        setting_set("share_port", str(int(port)))
    if name is not None:
        setting_set("share_name", name.strip()[:MAX_NAME])
    return settings()


def _secret() -> bytes:
    raw = setting_get("share_secret")
    if not raw:
        raw = base64.b64encode(os.urandom(32)).decode()
        setting_set("share_secret", raw)
    return base64.b64decode(raw)


def lan_addresses() -> List[str]:
    found: List[str] = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("10.255.255.255", 1))
        found.append(sock.getsockname()[0])
        sock.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith("127.") and addr not in found:
                found.append(addr)
    except OSError:
        pass
    return found


def base_urls() -> List[str]:
    port = settings()["port"]
    urls = [f"http://{addr}:{port}" for addr in lan_addresses()]
    host = socket.gethostname()
    if host and "." not in host:
        urls.append(f"http://{host}.local:{port}")
    return urls


def url_for(token: str) -> str:
    urls = base_urls()
    return f"{urls[0] if urls else 'http://localhost:' + str(settings()['port'])}/s/{token}"


def _shareable_ids(ids: List[int]) -> List[int]:
    from .. import vaultcrypt

    out = []
    for media_id in ids:
        row = q1(f"SELECT m.* FROM media m WHERE m.id=? AND {SHAREABLE}", (media_id,))
        if row is None or vaultcrypt.protected(row) or vaultcrypt.is_vaulted(media_id):
            continue
        out.append(media_id)
    return out


def create(kind: str, title: str, ids: Optional[List[int]] = None, album_id: Optional[int] = None,
           expires_days: Optional[float] = None, password: Optional[str] = None, allow_download: bool = True,
           allow_comments: bool = True, allow_contrib: bool = False, include_location: bool = False) -> Dict[str, Any]:
    token = secrets.token_urlsafe(18)
    expires = time.time() + expires_days * 86400 if expires_days else None
    share_id = ex("""INSERT INTO shares(token, kind, album_id, title, created_ts, expires_ts, password_hash, allow_download,
                     allow_comments, allow_contrib, include_location) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                  (token, kind, album_id, title.strip()[:120] or "Shared Photos", time.time(), expires,
                   hash_passkey(password) if password else None, int(allow_download), int(allow_comments),
                   int(allow_contrib and kind == "album"), int(include_location)))
    for pos, media_id in enumerate(_shareable_ids(ids or [])):
        ex("INSERT OR IGNORE INTO share_items(share_id, media_id, position) VALUES(?,?,?)", (share_id, media_id, pos))
    return describe(q1("SELECT * FROM shares WHERE id=?", (share_id,)))


def describe(row) -> Dict[str, Any]:
    d = dict(row)
    d.pop("password_hash", None)
    d["has_password"] = bool(row["password_hash"])
    d["url"] = url_for(row["token"])
    d["count"] = len(item_ids(row))
    d["unread"] = q1("SELECT COUNT(*) AS n FROM share_activity WHERE share_id=? AND owner=0 AND ts>?", (row["id"], row["seen_ts"]))["n"]
    if row["album_id"]:
        album = q1("SELECT name FROM albums WHERE id=?", (row["album_id"],))
        d["album_name"] = album["name"] if album else None
    return d


def listing() -> List[Dict[str, Any]]:
    return [describe(r) for r in q("SELECT * FROM shares WHERE revoked=0 ORDER BY created_ts DESC")]


def live(token: str):
    row = q1("SELECT * FROM shares WHERE token=? AND revoked=0", (token,))
    if row is None or (row["expires_ts"] and row["expires_ts"] < time.time()):
        return None
    if row["kind"] == "album":
        album = q1("SELECT is_private FROM albums WHERE id=?", (row["album_id"],))
        if album is None or album["is_private"]:
            return None
    return row


def item_ids(share) -> List[int]:
    key = (share["id"], share["kind"], share["album_id"])
    hit = _ids_cache.get(key)
    if hit is not None and time.time() - hit[0] < IDS_TTL_S:
        return hit[1]
    ids = _item_ids(share)
    if len(_ids_cache) > 64:
        _ids_cache.clear()
    _ids_cache[key] = (time.time(), ids)
    return ids


def forget_items(share_id: Optional[int] = None) -> None:
    for key in [k for k in _ids_cache if share_id is None or k[0] == share_id]:
        _ids_cache.pop(key, None)


def _item_ids(share) -> List[int]:
    if share["kind"] == "album":
        rows = q(f"""SELECT m.id FROM album_items ai JOIN media m ON m.id=ai.media_id
                     WHERE ai.album_id=? AND {SHAREABLE} ORDER BY ai.position, m.created_ts""", (share["album_id"],))
    else:
        rows = q(f"""SELECT m.id FROM share_items si JOIN media m ON m.id=si.media_id
                     WHERE si.share_id=? AND {SHAREABLE} ORDER BY si.position""", (share["id"],))
    return _shareable_ids([r["id"] for r in rows])


def allowed(share, media_id: int) -> bool:
    if media_id not in item_ids(share):
        return False
    return bool(_shareable_ids([media_id]))


def needs_unlock(share, cookie: Optional[str]) -> bool:
    if not share["password_hash"]:
        return False
    return not check_cookie(share, cookie)


def unlock(share, password: str) -> Optional[str]:
    if not share["password_hash"] or not verify_passkey(password, share["password_hash"]):
        return None
    expires = int(time.time()) + COOKIE_TTL
    body = f"{share['token']}|{expires}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def check_cookie(share, cookie: Optional[str]) -> bool:
    if not cookie or "." not in cookie:
        return False
    expires_raw, sig = cookie.split(".", 1)
    want = hmac.new(_secret(), f"{share['token']}|{expires_raw}".encode(), hashlib.sha256).hexdigest()
    try:
        fresh = int(expires_raw) >= time.time()
    except ValueError:
        return False
    return fresh and hmac.compare_digest(sig, want)


def items(share) -> List[Dict[str, Any]]:
    out = []
    for media_id in item_ids(share):
        row = q1("SELECT id, kind, width, height, duration, created_ts, title, caption FROM media WHERE id=?", (media_id,))
        likes = q1("SELECT COUNT(*) AS n FROM share_activity WHERE share_id=? AND media_id=? AND kind='like'", (share["id"], media_id))["n"]
        comments = q1("SELECT COUNT(*) AS n FROM share_activity WHERE share_id=? AND media_id=? AND kind='comment'", (share["id"], media_id))["n"]
        out.append({**dict(row), "likes": likes, "comments": comments})
    return out


def activity(share_id: int, media_id: Optional[int] = None, limit: int = 200) -> List[Dict[str, Any]]:
    if media_id is None:
        rows = q("SELECT * FROM share_activity WHERE share_id=? ORDER BY ts DESC LIMIT ?", (share_id, limit))
    else:
        rows = q("SELECT * FROM share_activity WHERE share_id=? AND media_id=? ORDER BY ts LIMIT ?", (share_id, media_id, limit))
    return [dict(r) for r in rows]


def post(share, kind: str, author: str, text: str = "", media_id: Optional[int] = None, owner: bool = False) -> Dict[str, Any]:
    author = (author or "").strip()[:MAX_NAME] or "Guest"
    text = (text or "").strip()[:MAX_TEXT]
    if kind == "comment" and not text:
        raise ValueError("Write something first")
    if kind == "like":
        existing = q1("SELECT id FROM share_activity WHERE share_id=? AND media_id=? AND kind='like' AND author=?",
                      (share["id"], media_id, author))
        if existing:
            ex("DELETE FROM share_activity WHERE id=?", (existing["id"],))
            return {"liked": False}
    act_id = ex("INSERT INTO share_activity(share_id, media_id, kind, author, text, ts, owner) VALUES(?,?,?,?,?,?,?)",
                (share["id"], media_id, kind, author, text or None, time.time(), int(owner)))
    return dict(q1("SELECT * FROM share_activity WHERE id=?", (act_id,)))


def contribute(share, path: str, author: str) -> Dict[str, Any]:
    from . import libraryfs

    result = libraryfs.import_one(path, move=True)
    media_id = result.get("media_id")
    if not media_id or result.get("status") != "imported" and not _shareable_ids([media_id]):
        return {"status": "received"}
    forget_items(share["id"])
    pos = q1("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM album_items WHERE album_id=?", (share["album_id"],))["p"]
    ex("INSERT OR IGNORE INTO album_items(album_id, media_id, position, added_ts) VALUES(?,?,?,?)",
       (share["album_id"], media_id, pos, time.time()))
    if q1("SELECT cover_media_id FROM albums WHERE id=?", (share["album_id"],))["cover_media_id"] is None:
        ex("UPDATE albums SET cover_media_id=? WHERE id=?", (media_id, share["album_id"]))
    post(share, "contrib", author, "", media_id)
    return result


def still_path(media_id: int, width: int) -> Optional[str]:
    from ..routers.render import _bucket, render_folder, render_image

    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    width = _bucket(width)
    stamp = hashlib.sha1(f"{row['edit_json'] or ''}|{row['edited_ts'] or 0}".encode()).hexdigest()[:12]
    cached = os.path.join(render_folder(), f"{media_id}_{width}_{stamp}.webp")
    if os.path.isfile(cached):
        return cached
    img, _ = render_image(row, width)
    if img is None:
        return None
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "WEBP", quality=88, method=4)
    tmp = cached + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(buf.getvalue())
    os.replace(tmp, cached)
    return cached


def download_path(share, media_id: int) -> Optional[str]:
    from . import libraryfs

    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    src = libraryfs.abs_path(row["rel_path"])
    trimmed = row["kind"] == "video" and (row["trim_in"] is not None or row["trim_out"] is not None)
    if share["include_location"] and not row["location_hidden"] and not row["edit_json"] and not trimmed:
        return src
    folder = os.path.join(cache_dir(), "share")
    os.makedirs(folder, exist_ok=True)
    stamp = hashlib.sha1(f"{row['edit_json'] or ''}|{row['edited_ts'] or 0}|{share['include_location']}|{row['trim_in']}|{row['trim_out']}".encode()).hexdigest()[:12]
    if row["kind"] == "video":
        out = os.path.join(folder, f"{media_id}_{stamp}{os.path.splitext(row['name'])[1].lower() or '.mp4'}")
        if not os.path.isfile(out):
            from ..dedup.visual import ffmpeg_path

            ff = ffmpeg_path()
            if not ff:
                return None
            tmp = out + ".part" + os.path.splitext(out)[1]
            args = [ff, "-y", "-v", "error"]
            if row["trim_in"] is not None:
                args += ["-ss", f"{float(row['trim_in']):.3f}"]
            if row["trim_out"] is not None:
                args += ["-to", f"{float(row['trim_out']):.3f}"]
            args += ["-i", src, "-map", "0:v:0", "-map", "0:a?", "-dn", "-c", "copy"]
            if not share["include_location"]:
                args += ["-map_metadata", "-1"]
            done = subprocess.run(args + [tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
            if done.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                return None
            os.replace(tmp, out)
        return out
    out = os.path.join(folder, f"{media_id}_{stamp}.jpg")
    if not os.path.isfile(out):
        from ..routers.render import render_image

        img, _ = render_image(row, 100000)
        if img is None:
            return None
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".jpg")
        os.close(fd)
        exif = gps_exif(row) if share["include_location"] else None
        if exif is not None:
            img.convert("RGB").save(tmp, "JPEG", quality=92, exif=exif)
        else:
            img.convert("RGB").save(tmp, "JPEG", quality=92)
        os.replace(tmp, out)
    return out


def gps_exif(row):
    if row["lat"] is None or row["lon"] is None or row["location_hidden"]:
        return None
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational

    def dms(value: float):
        value = abs(value)
        deg = int(value)
        minutes = int((value - deg) * 60)
        seconds = round(((value - deg) * 60 - minutes) * 60 * 1000)
        return (IFDRational(deg, 1), IFDRational(minutes, 1), IFDRational(seconds, 1000))

    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    gps[1] = "N" if row["lat"] >= 0 else "S"
    gps[2] = dms(row["lat"])
    gps[3] = "E" if row["lon"] >= 0 else "W"
    gps[4] = dms(row["lon"])
    return exif


def web_gallery(ids: List[int], title: str, dest: str, include_location: bool, state: Dict[str, Any]) -> None:
    import json
    import re
    import shutil

    from ..routers.render import render_image

    name = re.sub(r"[^\w .-]+", "", title).strip() or "Web Gallery"
    folder = os.path.join(dest, name)
    n = 1
    while os.path.exists(folder):
        n += 1
        folder = os.path.join(dest, f"{name} {n}")
    os.makedirs(os.path.join(folder, "photos"))
    os.makedirs(os.path.join(folder, "thumbs"))
    ok = _shareable_ids(ids)
    counts = {"written": 0, "skipped": len(ids) - len(ok)}
    state["counts"] = counts
    state["dest"] = folder
    fake = {"include_location": int(include_location), "allow_download": 1}
    entries = []
    for pos, media_id in enumerate(ok, start=1):
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        stem = f"{pos:04d}"
        if row["kind"] == "video":
            src = download_path(fake, media_id)
            if src is None:
                counts["skipped"] += 1
                continue
            full = f"photos/{stem}{os.path.splitext(src)[1]}"
            shutil.copy2(src, os.path.join(folder, full))
            thumb = thumbs.ensure_thumb(media_id, row["rel_path"], "video", 768)
            if thumb:
                from PIL import Image

                Image.open(thumb).convert("RGB").save(os.path.join(folder, f"thumbs/{stem}.jpg"), "JPEG", quality=85)
        else:
            img, _ = render_image(row, 2048)
            if img is None:
                counts["skipped"] += 1
                continue
            full = f"photos/{stem}.jpg"
            exif = gps_exif(row) if include_location else None
            if exif is not None:
                img.convert("RGB").save(os.path.join(folder, full), "JPEG", quality=90, exif=exif)
            else:
                img.convert("RGB").save(os.path.join(folder, full), "JPEG", quality=90)
            img.thumbnail((640, 640))
            img.convert("RGB").save(os.path.join(folder, f"thumbs/{stem}.jpg"), "JPEG", quality=82)
        entries.append({"full": full, "thumb": f"thumbs/{stem}.jpg", "kind": row["kind"], "title": row["title"] or "", "caption": row["caption"] or ""})
        counts["written"] += 1
    data = json.dumps({"title": title, "items": entries}).replace("</", "<\\/")
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(GALLERY.replace("{{title}}", html_escape(title)).replace("{{data}}", data))


def html_escape(text: str) -> str:
    import html

    return html.escape(text or "")


GALLERY = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{title}}</title>
<style>
:root { --bg: #0d0d0f; --panel: #17171a; --text: #f2f2f4; --muted: #a0a0a8; --layer-viewer: 10; color-scheme: dark; }
@media (prefers-color-scheme: light) { :root { --bg: #f6f6f7; --panel: #ffffff; --text: #18181b; --muted: #5d5d66; color-scheme: light; } }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 22px; margin: 20px 16px 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 4px; padding: 0 16px 40px; }
.grid a { display: block; aspect-ratio: 1; background: var(--panel); overflow: hidden; border-radius: 4px; }
.grid img { width: 100%; height: 100%; object-fit: cover; display: block; }
.view { position: fixed; inset: 0; z-index: var(--layer-viewer); background: rgba(0,0,0,.94); display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 8px; }
.view[hidden] { display: none; }
.view img, .view video { max-width: 96vw; max-height: 86vh; object-fit: contain; }
.view p { color: #ddd; margin: 0; max-width: 90vw; text-align: center; }
.view button { position: absolute; top: 12px; font: inherit; padding: 6px 12px; border-radius: 999px; border: 1px solid #444; background: #1b1b1e; color: #eee; cursor: pointer; }
.close { right: 12px; } .prev { left: 12px; } .next { left: 100px; }
</style></head><body>
<h1>{{title}}</h1><div class="grid" id="grid"></div>
<div class="view" id="view" hidden><button class="prev" type="button">Previous</button><button class="next" type="button">Next</button><button class="close" type="button">Close</button><div id="stage"></div><p id="cap"></p></div>
<script>
const D = {{data}};
const grid = document.getElementById("grid"), view = document.getElementById("view"), stage = document.getElementById("stage"), cap = document.getElementById("cap");
let at = -1;
D.items.forEach((it, i) => { const a = document.createElement("a"); a.href = it.full; const img = document.createElement("img"); img.src = it.thumb; img.alt = it.title; img.loading = "lazy"; a.append(img); a.onclick = (e) => { e.preventDefault(); show(i); }; grid.append(a); });
function show(i) { if (i < 0 || i >= D.items.length) return; at = i; const it = D.items[i]; const m = document.createElement(it.kind === "video" ? "video" : "img"); m.src = it.full; if (it.kind === "video") m.controls = true; stage.replaceChildren(m); cap.textContent = [it.title, it.caption].filter(Boolean).join(" · "); view.hidden = false; }
view.querySelector(".close").onclick = () => { view.hidden = true; stage.replaceChildren(); };
view.querySelector(".prev").onclick = () => show(at - 1); view.querySelector(".next").onclick = () => show(at + 1);
document.addEventListener("keydown", (e) => { if (view.hidden) return; if (e.key === "Escape") view.querySelector(".close").onclick(); if (e.key === "ArrowLeft") show(at - 1); if (e.key === "ArrowRight") show(at + 1); });
</script></body></html>"""


def qr_png(text: str, scale: int = 8) -> bytes:
    import cv2
    import numpy as np

    code = cv2.QRCodeEncoder.create().encode(text)
    code = np.pad(code, 4, constant_values=255)
    big = cv2.resize(code, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    ok, buf = cv2.imencode(".png", big)
    return buf.tobytes() if ok else b""
