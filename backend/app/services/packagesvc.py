import json
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
MIN_PASSWORD = 10
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
            edit_member = secrets.token_hex(16)
            members.append((edit_member, ext))
            state["external"] = {**state["external"], "member": edit_member}
        entry["edit"] = state
    if row["live_video_id"] and not payload["converted"]:
        video = q1("SELECT * FROM media WHERE id=?", (row["live_video_id"],))
        if video is not None:
            vp = _payload(video, include_location, work)
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
            marker = json.loads(zf.read(MARKER).decode("utf-8"))
    except Exception:
        return {"package": False}
    if marker.get("format") != FORMAT:
        return {"package": False}
    return {"package": True, "version": marker.get("version"), "files": len([n for n in names if NAME_RE.match(n)])}


def _read_manifest(zf) -> Dict[str, Any]:
    try:
        data = json.loads(zf.read(MANIFEST).decode("utf-8"))
    except RuntimeError as exc:
        raise PackageError("That password does not open this package") from exc
    except Exception as exc:
        if "password" in str(exc).lower() or "bad" in str(exc).lower():
            raise PackageError("That password does not open this package") from exc
        raise PackageError("This package is damaged") from exc
    if data.get("format") != FORMAT or not isinstance(data.get("items"), list):
        raise PackageError("This is not a DAM share package")
    return data


def check_password(path: str, password: str) -> Dict[str, Any]:
    pz = _zipper()
    with pz.AESZipFile(path) as zf:
        zf.setpassword(password.encode())
        data = _read_manifest(zf)
    return {"title": data.get("title"), "sender": data.get("sender"), "count": len(data["items"]),
            "album": (data.get("album") or {}).get("name"), "add_as": data.get("add_as")}


def _safe_name(name: Any) -> str:
    base = os.path.basename(str(name or "")).strip()
    base = SAFE_NAME.sub("_", base)
    return base[:180] or "photo"


def _import_member(zf, member: str, name: str, work: str) -> Dict[str, Any]:
    if not NAME_RE.match(str(member)):
        return {"status": "skipped"}
    folder = tempfile.mkdtemp(dir=work)
    local = os.path.join(folder, _safe_name(name))
    with zf.open(member) as src, open(local, "wb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    return libraryfs.import_one(local, move=True)


def _apply_meta(media_id: int, entry: Dict[str, Any]) -> None:
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    if row is None or row["private"] or row["hidden"]:
        return
    sets, vals = [], []
    for key in ("title", "caption", "alt_text", "label"):
        if entry.get(key) and not row[key]:
            sets.append(f"{key}=?")
            vals.append(str(entry[key])[:2000])
    if entry.get("rating") and not row["rating"]:
        sets.append("rating=?")
        vals.append(max(0, min(5, int(entry["rating"]))))
    if entry.get("favorite"):
        sets.append("favorite=1")
    if entry.get("lat") is not None and row["lat"] is None:
        sets.append("lat=?, lon=?")
        vals += [float(entry["lat"]), float(entry["lon"])]
    for key in ("trim_in", "trim_out"):
        if entry.get(key) is not None and row[key] is None and row["kind"] == "video":
            sets.append(f"{key}=?")
            vals.append(float(entry[key]))
    if sets:
        ex(f"UPDATE media SET {', '.join(sets)} WHERE id=?", vals + [media_id])
    for name in (entry.get("keywords") or [])[:200]:
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
            with zf.open(member) as src, open(os.path.join(edits_dir(), name), "wb") as dst:
                shutil.copyfileobj(src, dst)
            edit["external"] = {"file": name, "app": str(ext.get("app") or ""), "ts": time.time()}
    clean = {k: v for k, v in edit.items() if v not in (None, {}, [])}
    if clean:
        ex("UPDATE media SET edit_json=?, edited_ts=? WHERE id=?", (json.dumps(clean), time.time(), media_id))


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
            for entry in data["items"]:
                if not isinstance(entry, dict):
                    continue
                origin = str(entry.get("origin") or "").lower()
                known = q1("SELECT id FROM media WHERE sha256=? OR origin_sha=?", (origin, origin)) if ORIGIN_RE.match(origin) else None
                if known is not None:
                    result = {"status": "duplicate", "media_id": known["id"]}
                else:
                    try:
                        result = _import_member(zf, entry.get("member"), entry.get("name"), work)
                    except Exception:
                        counts["failed"] += 1
                        continue
                    if result.get("status") == "imported" and ORIGIN_RE.match(origin):
                        ex("UPDATE media SET origin_sha=? WHERE id=? AND sha256<>?", (origin, result["media_id"], origin))
                media_id = result.get("media_id")
                if not media_id:
                    counts["failed"] += 1
                    continue
                counts["imported" if result.get("status") == "imported" else "already"] += 1
                _apply_meta(media_id, entry)
                if entry.get("edit"):
                    _apply_edit(zf, media_id, entry["edit"], work)
                live = entry.get("live")
                if isinstance(live, dict):
                    try:
                        vres = _import_member(zf, live.get("member"), live.get("name"), work)
                        if vres.get("media_id"):
                            libraryfs.link_live(media_id, vres["media_id"])
                    except Exception:
                        pass
                visible = q1("SELECT private, hidden, trashed_ts FROM media WHERE id=?", (media_id,))
                if visible and not visible["private"] and not visible["hidden"] and not visible["trashed_ts"]:
                    imported_ids.append(media_id)
            kind = "album" if data.get("album") else (add_as or data.get("add_as") or "album")
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
    meta = data.get("album") or {}
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
    for note in notes[:5000]:
        if not isinstance(note, dict):
            continue
        nid = str(note.get("id") or "")
        text = str(note.get("text") or "").strip()[:MAX_NOTE]
        if not re.match(r"^[0-9a-f]{32}$", nid) or not text:
            continue
        if q1("SELECT 1 AS x FROM album_notes WHERE id=?", (nid,)):
            continue
        ex("INSERT INTO album_notes(id, album_id, author, text, ts, media_sha) VALUES(?,?,?,?,?,?)",
           (nid, album_id, str(note.get("author") or "Someone")[:60], text, float(note.get("ts") or time.time()),
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
