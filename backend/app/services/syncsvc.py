import json
import os
import shutil
import socket
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..db import ex, q, q1, reset_thread_conn, setting_get, setting_set
from . import libraryfs

CHANNELS = ("personal", "shared")
ROOT = "DAM Sync"
INTERVAL_S = 60
FIELDS = ("favorite", "rating", "label", "rejected", "title", "caption", "alt_text", "edit_json", "hidden", "trashed_ts",
          "created_ts", "lat", "lon", "location_hidden", "shared_lib")
SYNCABLE = "m.private=0 AND m.live_of IS NULL"

_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_wake = threading.Event()
_status: Dict[str, Dict[str, Any]] = {c: {} for c in CHANNELS}


def device_id() -> str:
    value = setting_get("sync_device_id")
    if not value:
        value = uuid.uuid4().hex
        setting_set("sync_device_id", value)
    return value


def device_name() -> str:
    return setting_get("sync_device_name") or socket.gethostname() or "This computer"


def _key(channel: str, name: str) -> str:
    return f"sync_{channel}_{name}"


def config(channel: str) -> Dict[str, Any]:
    folder = setting_get(_key(channel, "folder")) or ""
    return {"channel": channel, "folder": folder, "enabled": bool(folder) and setting_get(_key(channel, "enabled")) == "1",
            "last_push": float(setting_get(_key(channel, "push_ts")) or 0), "last_pull": float(setting_get(_key(channel, "pull_ts")) or 0),
            **_status.get(channel, {})}


def configure(channel: str, folder: Optional[str], enabled: bool) -> Dict[str, Any]:
    if folder is not None:
        folder = os.path.abspath(os.path.expanduser(folder)) if folder else ""
        if folder:
            os.makedirs(os.path.join(folder, ROOT), exist_ok=True)
        if folder != (setting_get(_key(channel, "folder")) or ""):
            setting_set(_key(channel, "folder"), folder)
            setting_set(_key(channel, "push_ts"), "0")
            setting_set(_key(channel, "pushed_once"), "0")
            for row in q("SELECT key FROM settings WHERE key LIKE ?", (_key(channel, "cursor_") + "%",)):
                ex("DELETE FROM settings WHERE key=?", (row["key"],))
    setting_set(_key(channel, "enabled"), "1" if enabled else "0")
    if enabled:
        start()
        _wake.set()
    return config(channel)


def _base(channel: str) -> str:
    return os.path.join(setting_get(_key(channel, "folder")) or "", ROOT)


def _object_path(base: str, sha: str, ext: str) -> str:
    return os.path.join(base, "objects", sha[:2], sha + ext.lower())


def _scope(channel: str) -> str:
    return SYNCABLE + (" AND (m.shared_lib=1 OR m.shared_origin IS NOT NULL)" if channel == "shared" else "")


def _carries_object(channel: str, row) -> bool:
    return not row["trashed_ts"] and not row["hidden"] and (channel != "shared" or bool(row["shared_lib"]))


def _record(row) -> Dict[str, Any]:
    fields = {k: row[k] for k in FIELDS}
    fields["keywords"] = [r["name"] for r in q("""SELECT k.name FROM media_keywords mk JOIN keywords k ON k.id=mk.keyword_id
                                                 WHERE mk.media_id=? ORDER BY k.name""", (row["id"],))]
    return {"op": "media", "sha": row["sha256"], "size": row["size"], "name": row["name"], "kind": row["kind"],
            "ts": row["meta_ts"], "origin": row["shared_origin"] or device_id(), "fields": fields}


def _vaulted(media_id: int) -> bool:
    from .. import vaultcrypt

    return vaultcrypt.is_vaulted(media_id)


def _put_object(base: str, row) -> bool:
    src = libraryfs.abs_path(row["rel_path"])
    dest = _object_path(base, row["sha256"], os.path.splitext(row["name"])[1])
    if os.path.isfile(dest):
        return True
    if not os.path.isfile(src):
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    shutil.copy2(src, tmp)
    os.replace(tmp, dest)
    return True


def _put_edit(base: str, edit_json: Optional[str]) -> None:
    from .extedit import edits_dir

    try:
        name = os.path.basename(((json.loads(edit_json or "{}") or {}).get("external") or {}).get("file") or "")
    except ValueError:
        return
    src = os.path.join(edits_dir(), name)
    if name and os.path.isfile(src):
        dest = os.path.join(base, "objects", "edits", name)
        if not os.path.isfile(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)


def push(channel: str) -> Dict[str, int]:
    base = _base(channel)
    me = device_id()
    since = float(setting_get(_key(channel, "push_ts")) or 0)
    first = setting_get(_key(channel, "pushed_once")) != "1"
    started = time.time()
    rows = q(f"SELECT m.* FROM media m WHERE {_scope(channel)} AND (m.meta_ts > ? OR ?) ORDER BY m.meta_ts", (since, int(first)))
    records: List[Dict[str, Any]] = []
    counts = {"media": 0, "objects": 0, "albums": 0}
    for row in rows:
        if _vaulted(row["id"]) or (first and not _carries_object(channel, row)):
            continue
        if _carries_object(channel, row):
            if not _put_object(base, row):
                continue
            counts["objects"] += 1
        _put_edit(base, row["edit_json"])
        records.append(_record(row))
        counts["media"] += 1
    if channel == "personal":
        for album in q("SELECT * FROM albums WHERE is_private=0 AND rules_json IS NULL AND (meta_ts > ? OR ?)", (since, int(first))):
            shas = [r["sha256"] for r in q(f"""SELECT m.sha256 FROM album_items ai JOIN media m ON m.id=ai.media_id
                                              WHERE ai.album_id=? AND {SYNCABLE} AND m.hidden=0 ORDER BY ai.position, ai.added_ts""", (album["id"],))]
            records.append({"op": "album", "uuid": album["uuid"], "name": album["name"], "items": shas, "ts": album["meta_ts"] or album["created_ts"]})
            counts["albums"] += 1
        for tomb in q("SELECT * FROM sync_tombstones WHERE ts > ? OR ?", (since, int(first))):
            records.append({"op": "album", "uuid": tomb["uuid"], "deleted": True, "ts": tomb["ts"]})
    _write_device(base, me)
    if records:
        folder = os.path.join(base, "journal", me)
        os.makedirs(folder, exist_ok=True)
        seq = int(setting_get(_key(channel, "seq")) or 0) + 1
        path = os.path.join(folder, f"{seq:08d}.jsonl")
        with open(path + ".tmp", "w", encoding="utf-8") as handle:
            for rec in records:
                handle.write(json.dumps(rec, separators=(",", ":")) + "\n")
        os.replace(path + ".tmp", path)
        setting_set(_key(channel, "seq"), str(seq))
    setting_set(_key(channel, "push_ts"), str(started - 1))
    setting_set(_key(channel, "pushed_once"), "1")
    return counts


def _write_device(base: str, me: str) -> None:
    folder = os.path.join(base, "devices")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, me + ".json")
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        json.dump({"id": me, "name": device_name(), "seen": time.time()}, handle)
    os.replace(path + ".tmp", path)


def devices(channel: str) -> List[Dict[str, Any]]:
    folder = os.path.join(_base(channel), "devices")
    out = []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                info = json.load(handle)
        except (OSError, ValueError):
            continue
        info["me"] = info.get("id") == device_id()
        out.append(info)
    return out


def _keywords(media_id: int, names: List[str]) -> None:
    ex("DELETE FROM media_keywords WHERE media_id=?", (media_id,))
    for name in names[:200]:
        name = str(name).strip()[:120]
        if not name:
            continue
        ex("INSERT OR IGNORE INTO keywords(name) VALUES(?)", (name,))
        kid = q1("SELECT id FROM keywords WHERE name=?", (name,))["id"]
        ex("INSERT OR IGNORE INTO media_keywords(media_id, keyword_id) VALUES(?,?)", (media_id, kid))


def _apply_media(channel: str, base: str, rec: Dict[str, Any]) -> bool:
    row = q1("SELECT * FROM media WHERE sha256=? AND size=?", (rec["sha"], rec["size"]))
    fields = rec.get("fields") or {}
    if row is None:
        if fields.get("trashed_ts") or fields.get("hidden"):
            return True
        if channel == "shared" and not fields.get("shared_lib"):
            return True
        src = _object_path(base, rec["sha"], os.path.splitext(rec["name"])[1])
        if not os.path.isfile(src):
            return False
        stage = tempfile.mkdtemp(prefix="dam-sync-")
        try:
            local = os.path.join(stage, os.path.basename(rec["name"]) or os.path.basename(src))
            shutil.copy2(src, local)
            result = libraryfs.import_one(local, move=True)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        media_id = result.get("media_id")
        if not media_id:
            return True
        ex("UPDATE media SET meta_ts=0, shared_origin=? WHERE id=?", (rec.get("origin") if channel == "shared" or fields.get("shared_lib") else None, media_id))
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        _imported.append(media_id)
    elif row["private"] or _vaulted(row["id"]):
        return True
    if channel == "shared" and not fields.get("shared_lib"):
        if not row["shared_lib"] or float(rec.get("ts") or 0) <= float(row["meta_ts"] or 0):
            return True
        if row["shared_origin"] == device_id():
            ex("UPDATE media SET shared_lib=0, meta_ts=? WHERE id=?", (rec["ts"], row["id"]))
        elif not row["trashed_ts"]:
            ex("UPDATE media SET shared_lib=0, trashed_ts=?, trash_reason=?, meta_ts=? WHERE id=?",
               (time.time(), "Removed from the Shared Library", rec["ts"], row["id"]))
        _touched.append(row["id"])
        return True
    if float(rec.get("ts") or 0) <= float(row["meta_ts"] or 0):
        return True
    edit = fields.get("edit_json")
    if edit:
        _fetch_edit(base, edit)
    sets = ", ".join(f"{k}=?" for k in FIELDS)
    values = [fields.get(k) for k in FIELDS]
    values = [0 if v is None and k in ("favorite", "rating", "rejected", "hidden", "location_hidden", "shared_lib") else v for k, v in zip(FIELDS, values)]
    ex(f"UPDATE media SET {sets}, meta_ts=?, edited_ts=CASE WHEN ? IS NULL THEN NULL ELSE ? END WHERE id=?",
       values + [rec["ts"], edit, rec["ts"], row["id"]])
    _keywords(row["id"], fields.get("keywords") or [])
    ex("UPDATE media SET meta_ts=? WHERE id=?", (rec["ts"], row["id"]))
    _touched.append(row["id"])
    return True


def _fetch_edit(base: str, edit_json: str) -> None:
    from .extedit import edits_dir

    try:
        name = os.path.basename(((json.loads(edit_json) or {}).get("external") or {}).get("file") or "")
    except ValueError:
        return
    src = os.path.join(base, "objects", "edits", name)
    dest = os.path.join(edits_dir(), name)
    if name and os.path.isfile(src) and not os.path.isfile(dest):
        os.makedirs(edits_dir(), exist_ok=True)
        shutil.copy2(src, dest)


def _apply_album(rec: Dict[str, Any]) -> bool:
    album = q1("SELECT * FROM albums WHERE uuid=?", (rec["uuid"],))
    if rec.get("deleted"):
        if album is not None and not album["is_private"]:
            ex("DELETE FROM album_items WHERE album_id=?", (album["id"],))
            ex("DELETE FROM albums WHERE id=?", (album["id"],))
            ex("DELETE FROM sync_tombstones WHERE uuid=?", (rec["uuid"],))
        return True
    if album is not None and (album["is_private"] or float(rec.get("ts") or 0) <= float(album["meta_ts"] or 0)):
        return True
    if album is None:
        if q1("SELECT 1 AS x FROM sync_tombstones WHERE uuid=?", (rec["uuid"],)):
            return True
        album_id = ex("INSERT INTO albums(name, created_ts, uuid) VALUES(?,?,?)", (rec.get("name") or "Album", time.time(), rec["uuid"]))
    else:
        album_id = album["id"]
        ex("UPDATE albums SET name=? WHERE id=?", (rec.get("name") or album["name"], album_id))
    ex("DELETE FROM album_items WHERE album_id=?", (album_id,))
    now = time.time()
    for pos, sha in enumerate(rec.get("items") or []):
        hit = q1("SELECT id FROM media WHERE sha256=? AND private=0", (sha,))
        if hit:
            ex("INSERT OR IGNORE INTO album_items(album_id, media_id, position, added_ts) VALUES(?,?,?,?)", (album_id, hit["id"], pos, now))
    first = q1("SELECT media_id FROM album_items WHERE album_id=? ORDER BY position LIMIT 1", (album_id,))
    ex("UPDATE albums SET meta_ts=?, cover_media_id=COALESCE(cover_media_id, ?) WHERE id=?", (rec["ts"], first["media_id"] if first else None, album_id))
    return True


_imported: List[int] = []
_touched: List[int] = []


def pull(channel: str) -> Dict[str, int]:
    base = _base(channel)
    me = device_id()
    journal = os.path.join(base, "journal")
    counts = {"applied": 0, "imported": 0, "waiting": 0}
    if not os.path.isdir(journal):
        return counts
    del _imported[:]
    del _touched[:]
    for dev in sorted(os.listdir(journal)):
        if dev == me or not os.path.isdir(os.path.join(journal, dev)):
            continue
        ckey = _key(channel, "cursor_" + dev)
        seq, line = _cursor(setting_get(ckey))
        files = sorted(f for f in os.listdir(os.path.join(journal, dev)) if f.endswith(".jsonl"))
        blocked = False
        for name in files:
            fseq = int(name.split(".")[0])
            if fseq < seq:
                continue
            with open(os.path.join(journal, dev, name), encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            start = line if fseq == seq else 0
            for i in range(start, len(lines)):
                try:
                    rec = json.loads(lines[i])
                except ValueError:
                    continue
                ok = _apply_media(channel, base, rec) if rec.get("op") == "media" else _apply_album(rec) if rec.get("op") == "album" and channel == "personal" else True
                if not ok:
                    counts["waiting"] += 1
                    setting_set(ckey, f"{fseq}:{i}")
                    blocked = True
                    break
                counts["applied"] += 1
            if blocked:
                break
            setting_set(ckey, f"{fseq + 1}:0")
    counts["imported"] = len(_imported)
    if _imported or _touched:
        _after_pull(list(_imported), list(_touched))
    setting_set(_key(channel, "pull_ts"), str(time.time()))
    return counts


def _cursor(raw: Optional[str]) -> Tuple[int, int]:
    try:
        seq, line = (raw or "0:0").split(":")
        return int(seq), int(line)
    except ValueError:
        return 0, 0


def _after_pull(imported: List[int], touched: List[int]) -> None:
    from ..routers.edit import invalidate

    for media_id in touched:
        try:
            invalidate(media_id)
        except Exception:
            pass
    if imported:
        from . import followon

        followon.start_after_import({"imported": len(imported)})


def run_once() -> None:
    for channel in CHANNELS:
        conf = config(channel)
        if not conf["enabled"]:
            continue
        if not os.path.isdir(conf["folder"]):
            _status[channel] = {"error": "The sync folder is not reachable", "ts": time.time()}
            continue
        try:
            pulled = pull(channel)
            pushed = push(channel)
            _status[channel] = {"error": None, "ts": time.time(), "pushed": pushed, "pulled": pulled}
        except Exception as exc:
            _status[channel] = {"error": str(exc)[:200], "ts": time.time()}


def _loop() -> None:
    while True:
        try:
            with _lock:
                run_once()
        finally:
            reset_thread_conn()
        _wake.wait(INTERVAL_S)
        _wake.clear()
        if not any(config(c)["enabled"] for c in CHANNELS):
            global _thread
            _thread = None
            reset_thread_conn()
            return


def start() -> None:
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_loop, name="DAM-sync", daemon=True)
        _thread.start()


def sync_now() -> None:
    start()
    _wake.set()


def ensure() -> None:
    if any(config(c)["enabled"] for c in CHANNELS):
        start()


def set_shared(ids: List[int], shared: bool) -> int:
    changed = 0
    me = device_id()
    for media_id in ids:
        row = q1("SELECT id, private, shared_lib FROM media WHERE id=?", (media_id,))
        if row is None or row["private"] or _vaulted(media_id) or bool(row["shared_lib"]) == shared:
            continue
        ex("UPDATE media SET shared_lib=?, shared_origin=COALESCE(shared_origin, ?) WHERE id=?", (int(shared), me, media_id))
        changed += 1
    if changed:
        _wake.set()
    return changed
