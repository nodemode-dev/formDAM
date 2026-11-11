import json
import math
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from ..config import cache_dir
from ..db import ex, q, q1
from . import gpsscrub, libraryfs

FORMAT = "formdam-share"
VERSION = 1
MARKER = "formdam-share.json"
MANIFEST = "manifest"
MIN_PASSWORD = 16
MAX_MARKER = 4096
MAX_MANIFEST = 16 * 1024 * 1024
MAX_MEMBER = 8 * 1024 ** 3
DISK_MARGIN = 1024 ** 3
NAME_RE = re.compile(r"^[0-9a-f]{32}$")
ORIGIN_RE = re.compile(r"^[0-9a-f]{64}$")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SAFE_NAME = re.compile(r"[^\w .()+,-]+")
SHAREABLE = "m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL"
MAX_NOTE = 1000


class PackageError(Exception):
    pass


def new_password() -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(5)) for _ in range(5))


def incoming_dir() -> str:
    path = os.path.join(cache_dir(), "incoming")
    os.makedirs(path, exist_ok=True)
    return path


def _zipper():
    import pyzipper

    return pyzipper


def _read_capped(zf, name: str, cap: int) -> bytes:
    if zf.getinfo(name).file_size > cap:
        raise PackageError("This package is damaged or too large to open")
    with zf.open(name) as handle:
        data = handle.read(cap + 1)
    if len(data) > cap:
        raise PackageError("This package is damaged or too large to open")
    return data


def _copy_capped(zf, member: str, dest: str) -> None:
    cap = min(zf.getinfo(member).file_size, MAX_MEMBER)
    written = 0
    with zf.open(member) as src, open(dest, "wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > cap:
                raise PackageError("A file in this package is larger than it claims")
            dst.write(chunk)


def _check_space(zf) -> None:
    need = sum(info.file_size for info in zf.infolist() if NAME_RE.match(info.filename))
    if any(info.file_size > MAX_MEMBER for info in zf.infolist()):
        raise PackageError("A file in this package is too large to open")
    if need + DISK_MARGIN > shutil.disk_usage(cache_dir()).free:
        raise PackageError("There is not enough free disk space to open this package")


def _clean_file(src: str, work: str) -> str:
    target = os.path.join(work, secrets.token_hex(8) + os.path.splitext(src)[1].lower())
    with open(src, "rb") as handle:
        clean = gpsscrub.scrub(handle.read())
    with open(target, "wb") as handle:
        handle.write(clean)
    if gpsscrub.has_gps(target) is False:
        return target
    from PIL import Image

    rendered = os.path.join(work, secrets.token_hex(8) + ".jpg")
    with Image.open(src) as img:
        img.convert("RGB").save(rendered, "JPEG", quality=95)
    if gpsscrub.has_gps(rendered):
        raise PackageError("Location could not be removed from an edited version")
    return rendered


def _shareable(ids: List[int]) -> List[int]:
    from .. import vaultcrypt

    out = []
    for media_id in ids:
        row = q1(f"SELECT m.* FROM media m WHERE m.id=? AND {SHAREABLE}", (media_id,))
        if row is None or vaultcrypt.protected(row) or vaultcrypt.is_vaulted(media_id):
            continue
        out.append(media_id)
    return out


def _keywords(media_id: int) -> List[str]:
    return [r["name"] for r in q("""SELECT k.name FROM media_keywords mk JOIN keywords k ON k.id=mk.keyword_id
                                    WHERE mk.media_id=? ORDER BY k.name""", (media_id,))]


def _strip_video(src: str, dest: str) -> bool:
    from ..dedup.visual import ffmpeg_path

    ff = ffmpeg_path()
    if not ff:
        return False
    done = subprocess.run([ff, "-y", "-v", "error", "-i", src, "-map", "0:v", "-map", "0:a?", "-dn", "-map_metadata", "-1",
                           "-c", "copy", dest], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    return done.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0


def _payload(row, include_location: bool, work: str) -> Dict[str, Any]:
    src = libraryfs.abs_path(row["rel_path"])
    if include_location and not row["location_hidden"]:
        return {"path": src, "name": row["name"], "converted": False}
    target = os.path.join(work, secrets.token_hex(8) + os.path.splitext(row["name"])[1].lower())
    if row["kind"] == "video":
        if _strip_video(src, target):
            return {"path": target, "name": row["name"], "converted": False}
        raise PackageError(f"{row['name']}: location could not be removed from this video (ffmpeg is needed)")
    with open(src, "rb") as handle:
        clean = gpsscrub.scrub(handle.read())
    with open(target, "wb") as handle:
        handle.write(clean)
    found = gpsscrub.has_gps(target)
    if found is False or (found is None and row["lat"] is None):
        return {"path": target, "name": row["name"], "converted": False}
    from ..routers.render import render_image

    img, _ = render_image(row, 100000)
    if img is None:
        raise PackageError(f"{row['name']}: location could not be removed")
    stem = os.path.splitext(row["name"])[0]
    target = os.path.join(work, secrets.token_hex(8) + ".jpg")
    img.convert("RGB").save(target, "JPEG", quality=95)
    return {"path": target, "name": stem + ".jpg", "converted": True}


def _entry(row, include_location: bool, work: str, members: List[Any]) -> Dict[str, Any]:
    from .extedit import external_path

    payload = _payload(row, include_location, work)
    member = secrets.token_hex(16)
    members.append((member, payload["path"]))
    entry: Dict[str, Any] = {
        "member": member, "name": payload["name"], "origin": row["origin_sha"] or row["sha256"], "kind": row["kind"], "created_ts": row["created_ts"],
        "title": row["title"], "caption": row["caption"], "alt_text": row["alt_text"], "rating": row["rating"],
        "favorite": row["favorite"], "label": row["label"], "keywords": _keywords(row["id"]),
        "trim_in": row["trim_in"], "trim_out": row["trim_out"],
    }
    if include_location and not row["location_hidden"] and row["lat"] is not None:
        entry["lat"], entry["lon"] = row["lat"], row["lon"]
    if not payload["converted"] and row["edit_json"]:
        try:
            state = json.loads(row["edit_json"])
        except ValueError:
            state = {}
        ext = external_path(state)
        if ext:
            if not include_location or row["location_hidden"]:
                ext = _clean_file(ext, work)
            edit_member = secrets.token_hex(16)
            members.append((edit_member, ext))
            state["external"] = {**state["external"], "member": edit_member, "file": os.path.basename(ext)}
        entry["edit"] = state
    if row["live_video_id"] and not payload["converted"]:
        video = q1("SELECT * FROM media WHERE id=?", (row["live_video_id"],))
        if video is not None:
            vp = _payload(video, include_location and not row["location_hidden"], work)
            vmember = secrets.token_hex(16)
            members.append((vmember, vp["path"]))
            entry["live"] = {"member": vmember, "name": vp["name"]}
    return entry


def ensure_album_share(album_id: int) -> str:
    row = q1("SELECT share_uuid FROM albums WHERE id=?", (album_id,))
    if row["share_uuid"]:
        return row["share_uuid"]
    value = uuid.uuid4().hex
    ex("UPDATE albums SET share_uuid=? WHERE id=?", (value, album_id))
    return value


def build(ids: List[int], password: str, title: str, dest: str, include_location: bool, add_as: str,
          album_id: Optional[int], sender: str, state: Dict[str, Any]) -> None:
    if len(password) < MIN_PASSWORD:
        raise PackageError(f"Use a password of at least {MIN_PASSWORD} characters")
    pz = _zipper()
    album = None
    if album_id is not None:
        album = q1("SELECT * FROM albums WHERE id=?", (album_id,))
        if album is None or album["is_private"] or album["rules_json"]:
            raise PackageError("Only plain, non-private albums can be shared")
        ids = [r["media_id"] for r in q("SELECT media_id FROM album_items WHERE album_id=? ORDER BY position, added_ts", (album_id,))]
    keep = _shareable(ids)
    counts = {"items": 0, "skipped": len(ids) - len(keep), "converted": 0}
    state["counts"] = counts
    if not keep:
        raise PackageError("Nothing to share: private, hidden and deleted items are never shared")
    work = tempfile.mkdtemp(prefix="dam-pack-")
    try:
        members: List[Any] = []
        entries = []
        for media_id in keep:
            row = q1("SELECT * FROM media WHERE id=?", (media_id,))
            entry = _entry(row, include_location, work, members)
            counts["items"] += 1
            counts["converted"] += int(entry["name"] != row["name"])
            entries.append(entry)
        package_id = uuid.uuid4().hex
        manifest: Dict[str, Any] = {"format": FORMAT, "version": VERSION, "package_id": package_id, "created_ts": time.time(),
                                    "sender": sender, "title": title or (album["name"] if album else "Shared Photos"),
                                    "add_as": "album" if album else add_as, "items": entries}
        if album is not None:
            manifest["album"] = {"share_id": ensure_album_share(album["id"]), "name": album["name"]}
            manifest["notes"] = [dict(r) for r in q("SELECT id, author, text, ts, media_sha FROM album_notes WHERE album_id=? ORDER BY ts", (album["id"],))]
        name = SAFE_NAME.sub("", manifest["title"]).strip() or "Shared Photos"
        os.makedirs(dest, exist_ok=True)
        out = os.path.join(dest, f"{name}.zip")
        n = 1
        while os.path.exists(out):
            n += 1
            out = os.path.join(dest, f"{name} {n}.zip")
        tmp = out + ".part"
        with pz.AESZipFile(tmp, "w", compression=pz.ZIP_STORED) as zf:
            zf.writestr(MARKER, json.dumps({"format": FORMAT, "version": VERSION}))
            zf.setpassword(password.encode())
            zf.setencryption(pz.WZ_AES, nbits=256)
            zf.writestr(MANIFEST, json.dumps(manifest), compress_type=pz.ZIP_DEFLATED)
            for member, path in members:
                zf.write(path, member)
        os.replace(tmp, out)
        ex("""INSERT INTO share_packages(package_id, direction, kind, title, album_id, count, sender, path, created_ts)
              VALUES(?,?,?,?,?,?,?,?,?)""", (package_id, "out", "album" if album else add_as, manifest["title"], album_id,
                                              counts["items"], sender, out, time.time()))
        state["path"] = out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def inspect(path: str) -> Dict[str, Any]:
    pz = _zipper()
    try:
        with pz.AESZipFile(path) as zf:
            names = zf.namelist()
            if MARKER not in names or MANIFEST not in names:
                return {"package": False}
            marker = json.loads(_read_capped(zf, MARKER, MAX_MARKER).decode("utf-8"))
    except Exception:
        return {"package": False}
    if not isinstance(marker, dict) or marker.get("format") != FORMAT:
        return {"package": False}
    return {"package": True, "version": marker.get("version"), "files": len([n for n in names if NAME_RE.match(n)])}


def _read_manifest(zf) -> Dict[str, Any]:
    try:
        data = json.loads(_read_capped(zf, MANIFEST, MAX_MANIFEST).decode("utf-8"))
    except PackageError:
        raise
    except RuntimeError as exc:
        raise PackageError("That password does not open this package") from exc
    except Exception as exc:
        if "password" in str(exc).lower() or "bad" in str(exc).lower():
            raise PackageError("That password does not open this package") from exc
        raise PackageError("This package is damaged") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("items"), list):
        raise PackageError("This is not a formDAM share package")
    return data


def check_password(path: str, password: str) -> Dict[str, Any]:
    pz = _zipper()
    with pz.AESZipFile(path) as zf:
        zf.setpassword(password.encode())
        data = _read_manifest(zf)
    return {"title": str(data.get("title") or "")[:120], "sender": str(data.get("sender") or "")[:60], "count": len(data["items"]),
            "album": str(data["album"].get("name") or "")[:120] if isinstance(data.get("album"), dict) else None,
            "add_as": data.get("add_as") if data.get("add_as") in ("album", "stack") else "album"}


def _safe_name(name: Any) -> str:
    base = os.path.basename(str(name or "")).strip()
    base = SAFE_NAME.sub("_", base)
    return base[:180] or "photo"


def _import_member(zf, member: str, name: str, work: str) -> Dict[str, Any]:
    if not NAME_RE.match(str(member)):
        return {"status": "skipped"}
    folder = tempfile.mkdtemp(dir=work)
    local = os.path.join(folder, _safe_name(name))
    _copy_capped(zf, member, local)
    return libraryfs.import_one(local, move=True)


def _number(value: Any, low: float, high: float) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and low <= value <= high else None


def _apply_meta(media_id: int, entry: Dict[str, Any]) -> None:
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    if row is None or row["private"] or row["hidden"]:
        return
    sets, vals = [], []
    for key in ("title", "caption", "alt_text", "label"):
        if entry.get(key) and not row[key]:
            sets.append(f"{key}=?")
            vals.append(str(entry[key])[:2000])
    rating = _number(entry.get("rating"), 0, 5)
    if rating and not row["rating"]:
        sets.append("rating=?")
        vals.append(int(rating))
    if entry.get("favorite") is True or entry.get("favorite") == 1:
        sets.append("favorite=1")
    lat, lon = _number(entry.get("lat"), -90, 90), _number(entry.get("lon"), -180, 180)
    if lat is not None and lon is not None and row["lat"] is None:
        sets.append("lat=?, lon=?")
        vals += [lat, lon]
    for key in ("trim_in", "trim_out"):
        value = _number(entry.get(key), 0, 1e7)
        if value is not None and row[key] is None and row["kind"] == "video":
            sets.append(f"{key}=?")
            vals.append(value)
    if sets:
        ex(f"UPDATE media SET {', '.join(sets)} WHERE id=?", vals + [media_id])
    words = entry.get("keywords")
    for name in (words if isinstance(words, list) else [])[:200]:
        name = str(name).strip()[:120]
        if name:
            ex("INSERT OR IGNORE INTO keywords(name) VALUES(?)", (name,))
            kid = q1("SELECT id FROM keywords WHERE name=?", (name,))["id"]
            ex("INSERT OR IGNORE INTO media_keywords(media_id, keyword_id) VALUES(?,?)", (media_id, kid))


def _apply_edit(zf, media_id: int, edit: Dict[str, Any], work: str) -> None:
    from .extedit import edits_dir

    row = q1("SELECT edit_json, kind FROM media WHERE id=?", (media_id,))
    if row is None or row["edit_json"] or row["kind"] != "image" or not isinstance(edit, dict):
        return
    ext = edit.get("external")
    if isinstance(ext, dict):
        member = str(ext.get("member") or "")
        if not NAME_RE.match(member):
            edit.pop("external", None)
        else:
            os.makedirs(edits_dir(), exist_ok=True)
            name = f"{media_id}-shared-{secrets.token_hex(4)}{os.path.splitext(str(ext.get('file') or '.jpg'))[1][:6] or '.jpg'}"
            _copy_capped(zf, member, os.path.join(edits_dir(), name))
            edit["external"] = {"file": name, "app": str(ext.get("app") or ""), "ts": time.time()}
    from .editsvc import sanitize_state

    clean = sanitize_state({k: v for k, v in edit.items() if v not in (None, {}, [])})
    if clean:
        ex("UPDATE media SET edit_json=?, edited_ts=? WHERE id=?", (json.dumps(clean), time.time(), media_id))


def _open_entry(zf, entry: Dict[str, Any], work: str, counts: Dict[str, int]) -> Optional[int]:
    origin = str(entry.get("origin") or "").lower()
    known = q1("SELECT id FROM media WHERE sha256=? OR origin_sha=?", (origin, origin)) if ORIGIN_RE.match(origin) else None
    if known is not None:
        counts["already"] += 1
        return known["id"]
    result = _import_member(zf, entry.get("member"), entry.get("name"), work)
    media_id = result.get("media_id")
    if not media_id:
        counts["failed"] += 1
        return None
    if result.get("status") != "imported":
        counts["already"] += 1
        return media_id
    if ORIGIN_RE.match(origin):
        ex("UPDATE media SET origin_sha=? WHERE id=? AND sha256<>?", (origin, media_id, origin))
    counts["imported"] += 1
    _apply_meta(media_id, entry)
    if isinstance(entry.get("edit"), dict):
        _apply_edit(zf, media_id, entry["edit"], work)
    live = entry.get("live")
    if isinstance(live, dict):
        try:
            vres = _import_member(zf, live.get("member"), live.get("name"), work)
            if vres.get("status") == "imported" and vres.get("media_id"):
                libraryfs.link_live(media_id, vres["media_id"])
        except Exception:
            pass
    return media_id


def open_package(path: str, password: str, add_as: Optional[str], state: Dict[str, Any]) -> None:
    pz = _zipper()
    counts = {"imported": 0, "already": 0, "failed": 0, "notes": 0}
    state["counts"] = counts
    work = tempfile.mkdtemp(prefix="dam-open-")
    imported_ids: List[int] = []
    try:
        with pz.AESZipFile(path) as zf:
            zf.setpassword(password.encode())
            data = _read_manifest(zf)
            _check_space(zf)
            for entry in data["items"][:20000]:
                if not isinstance(entry, dict):
                    continue
                try:
                    media_id = _open_entry(zf, entry, work, counts)
                except Exception:
                    counts["failed"] += 1
                    continue
                if not media_id:
                    continue
                visible = q1("SELECT private, hidden, trashed_ts FROM media WHERE id=?", (media_id,))
                if visible and not visible["private"] and not visible["hidden"] and not visible["trashed_ts"]:
                    imported_ids.append(media_id)
            kind = "album" if isinstance(data.get("album"), dict) else (add_as if add_as in ("album", "stack") else "album")
            album_id, stack_id = None, None
            if kind == "stack" and len(imported_ids) > 1:
                from . import stacksvc

                stack_id = stacksvc.create(imported_ids, imported_ids[0], "manual")
            else:
                album_id = _album_for(data, imported_ids)
                counts["notes"] = _merge_notes(album_id, data.get("notes") or [])
            ex("""INSERT INTO share_packages(package_id, direction, kind, title, album_id, stack_id, count, sender, created_ts)
                  VALUES(?,?,?,?,?,?,?,?,?)""", (str(data.get("package_id") or "")[:64], "in", kind, str(data.get("title") or "")[:120],
                                                album_id, stack_id, len(imported_ids), str(data.get("sender") or "")[:60], time.time()))
            state["album_id"], state["stack_id"] = album_id, stack_id
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if imported_ids:
        from . import followon

        followon.start_after_import({"imported": counts["imported"]})
    try:
        os.unlink(path)
    except OSError:
        pass


def _album_for(data: Dict[str, Any], ids: List[int]) -> int:
    meta = data.get("album") if isinstance(data.get("album"), dict) else {}
    share_id = str(meta.get("share_id") or "")
    album = None
    if re.match(r"^[0-9a-f]{32}$", share_id):
        album = q1("SELECT * FROM albums WHERE share_uuid=?", (share_id,))
        if album is not None and (album["is_private"] or album["rules_json"]):
            album = None
            share_id = ""
    else:
        share_id = ""
    if album is None:
        name = str(meta.get("name") or data.get("title") or "Shared Photos")[:120]
        album_id = ex("INSERT INTO albums(name, created_ts, share_uuid) VALUES(?,?,?)", (name, time.time(), share_id or None))
    else:
        album_id = album["id"]
    pos = q1("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM album_items WHERE album_id=?", (album_id,))["p"]
    for media_id in ids:
        if q1("SELECT 1 AS x FROM album_items WHERE album_id=? AND media_id=?", (album_id, media_id)) is None:
            ex("INSERT INTO album_items(album_id, media_id, position, added_ts) VALUES(?,?,?,?)", (album_id, media_id, pos, time.time()))
            pos += 1
    if ids and q1("SELECT cover_media_id FROM albums WHERE id=?", (album_id,))["cover_media_id"] is None:
        ex("UPDATE albums SET cover_media_id=? WHERE id=?", (ids[0], album_id))
    return album_id


def _merge_notes(album_id: int, notes: List[Any]) -> int:
    added = 0
    for note in (notes if isinstance(notes, list) else [])[:5000]:
        if not isinstance(note, dict):
            continue
        nid = str(note.get("id") or "")
        text = str(note.get("text") or "").strip()[:MAX_NOTE]
        if not re.match(r"^[0-9a-f]{32}$", nid) or not text:
            continue
        if q1("SELECT 1 AS x FROM album_notes WHERE id=?", (nid,)):
            continue
        ex("INSERT INTO album_notes(id, album_id, author, text, ts, media_sha) VALUES(?,?,?,?,?,?)",
           (nid, album_id, str(note.get("author") or "Someone")[:60], text, _number(note.get("ts"), 0, 4e9) or time.time(),
            str(note.get("media_sha") or "")[:64] or None))
        added += 1
    return added


def add_note(album_id: int, author: str, text: str) -> Dict[str, Any]:
    text = text.strip()[:MAX_NOTE]
    if not text:
        raise PackageError("Write something first")
    nid = uuid.uuid4().hex
    ex("INSERT INTO album_notes(id, album_id, author, text, ts, mine) VALUES(?,?,?,?,?,1)", (nid, album_id, author[:60], text, time.time()))
    return dict(q1("SELECT * FROM album_notes WHERE id=?", (nid,)))
