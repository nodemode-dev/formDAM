import os
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

from .config import db_path, library_root

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS media(
  id INTEGER PRIMARY KEY,
  sha256 TEXT NOT NULL,
  rel_path TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  size INTEGER NOT NULL,
  kind TEXT NOT NULL,
  mime TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  duration REAL,
  created_ts REAL NOT NULL,
  created_src TEXT NOT NULL,
  imported_ts REAL NOT NULL,
  favorite INTEGER NOT NULL DEFAULT 0,
  private INTEGER NOT NULL DEFAULT 0,
  trashed_ts REAL,
  trash_reason TEXT,
  viewed_ts REAL,
  is_screenshot INTEGER NOT NULL DEFAULT 0,
  is_screen_rec INTEGER NOT NULL DEFAULT 0,
  face_state INTEGER NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  ocr_text TEXT,
  live_video_id INTEGER,
  live_of INTEGER,
  UNIQUE(sha256, size)
);
CREATE INDEX IF NOT EXISTS idx_media_created ON media(created_ts DESC);
CREATE INDEX IF NOT EXISTS idx_media_trashed ON media(trashed_ts);
CREATE INDEX IF NOT EXISTS idx_media_face ON media(face_state);
CREATE TABLE IF NOT EXISTS albums(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  created_ts REAL NOT NULL,
  is_private INTEGER NOT NULL DEFAULT 0,
  passkey_hash TEXT,
  cover_media_id INTEGER,
  position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS album_items(
  album_id INTEGER NOT NULL,
  media_id INTEGER NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  added_ts REAL NOT NULL,
  PRIMARY KEY(album_id, media_id)
);
CREATE TABLE IF NOT EXISTS people(
  id INTEGER PRIMARY KEY,
  name TEXT,
  cover_face_id INTEGER,
  created_ts REAL NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0,
  cover_locked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS faces(
  id INTEGER PRIMARY KEY,
  media_id INTEGER NOT NULL,
  frame_ts REAL NOT NULL DEFAULT 0,
  x REAL NOT NULL, y REAL NOT NULL, w REAL NOT NULL, h REAL NOT NULL,
  quality REAL NOT NULL DEFAULT 0,
  embedding BLOB NOT NULL,
  person_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_faces_media ON faces(media_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
CREATE TABLE IF NOT EXISTS keywords(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS media_keywords(
  media_id INTEGER NOT NULL, keyword_id INTEGER NOT NULL, PRIMARY KEY(media_id, keyword_id)
);
CREATE TABLE IF NOT EXISTS dup_sets(
  id INTEGER PRIMARY KEY,
  job_ts REAL NOT NULL,
  match_kind TEXT NOT NULL,
  similarity INTEGER NOT NULL,
  keeper_media_id INTEGER NOT NULL,
  resolved_ts REAL
);
CREATE TABLE IF NOT EXISTS dup_members(
  set_id INTEGER NOT NULL,
  media_id INTEGER NOT NULL,
  similarity INTEGER NOT NULL,
  PRIMARY KEY(set_id, media_id)
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


LEGACY_CATALOG = "damp.db"
WAL_TRIES = 10
_adopt_lock = threading.Lock()


def _adopt_legacy_catalog() -> None:
    target = db_path()
    legacy = os.path.join(library_root(), LEGACY_CATALOG)
    with _adopt_lock:
        if os.path.exists(target) or not os.path.exists(legacy):
            return
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(legacy + suffix):
                os.replace(legacy + suffix, target + suffix)


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    path = db_path()
    if conn is not None and getattr(_local, "path", path) == path:
        return conn
    if conn is not None:
        conn.close()
        _local.conn = None
    os.makedirs(library_root(), exist_ok=True)
    _adopt_legacy_catalog()
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    for attempt in range(WAL_TRIES):
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == WAL_TRIES - 1:
                conn.close()
                raise
            time.sleep(0.05 * (attempt + 1))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    _local.conn = conn
    _local.path = path
    return conn


SCHEMA_VERSION = 11

MEDIA_V5_COLUMNS = (
    "make TEXT", "model TEXT", "lens TEXT", "focal REAL", "focal35 REAL", "aperture REAL", "shutter REAL",
    "iso INTEGER", "flash INTEGER", "orientation INTEGER", "lat REAL", "lon REAL", "alt REAL",
    "place TEXT", "admin TEXT", "country TEXT", "location_hidden INTEGER NOT NULL DEFAULT 0",
    "content_id TEXT", "burst_id TEXT", "camera_type TEXT", "capture_type TEXT", "fps REAL",
    "is_raw INTEGER NOT NULL DEFAULT 0", "is_panorama INTEGER NOT NULL DEFAULT 0",
    "is_selfie INTEGER NOT NULL DEFAULT 0", "is_portrait INTEGER NOT NULL DEFAULT 0",
    "is_slomo INTEGER NOT NULL DEFAULT 0", "exif_json TEXT", "meta_ver INTEGER NOT NULL DEFAULT 0",
    "rating INTEGER NOT NULL DEFAULT 0", "label TEXT", "rejected INTEGER NOT NULL DEFAULT 0",
    "title TEXT", "caption TEXT", "alt_text TEXT", "iptc_json TEXT",
    "edit_json TEXT", "edited_ts REAL", "trim_in REAL", "trim_out REAL",
    "stack_id INTEGER", "batch_id INTEGER", "referenced INTEGER NOT NULL DEFAULT 0",
    "clip_state INTEGER NOT NULL DEFAULT 0", "orig_created_ts REAL", "xmp_ts REAL",
)

SYNC_STAMP = "(julianday('now') - 2440587.5) * 86400.0"
SYNC_MEDIA_COLUMNS = ("favorite, rating, label, rejected, title, caption, alt_text, edit_json, hidden, trashed_ts, "
                      "created_ts, lat, lon, location_hidden, shared_lib, private, trim_in, trim_out")

MIGRATIONS = {
    11: [
        "ALTER TABLE media ADD COLUMN origin_sha TEXT",
        "CREATE INDEX IF NOT EXISTS idx_media_origin ON media(origin_sha)",
        "ALTER TABLE albums ADD COLUMN share_uuid TEXT",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_albums_share_uuid ON albums(share_uuid)",
        """CREATE TABLE IF NOT EXISTS album_notes(
             id TEXT PRIMARY KEY, album_id INTEGER NOT NULL, author TEXT NOT NULL, text TEXT NOT NULL, ts REAL NOT NULL,
             media_sha TEXT, mine INTEGER NOT NULL DEFAULT 0)""",
        "CREATE INDEX IF NOT EXISTS idx_album_notes ON album_notes(album_id, ts)",
        """CREATE TABLE IF NOT EXISTS share_packages(
             id INTEGER PRIMARY KEY, package_id TEXT NOT NULL, direction TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
             album_id INTEGER, stack_id INTEGER, count INTEGER NOT NULL DEFAULT 0, sender TEXT, path TEXT, created_ts REAL NOT NULL)""",
        "DROP TABLE IF EXISTS share_items",
        "DROP TABLE IF EXISTS share_activity",
        "DROP TABLE IF EXISTS shares",
    ],
    10: [
        "ALTER TABLE media ADD COLUMN meta_ts REAL NOT NULL DEFAULT 0",
        "ALTER TABLE media ADD COLUMN shared_lib INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE media ADD COLUMN shared_origin TEXT",
        "ALTER TABLE albums ADD COLUMN uuid TEXT",
        "ALTER TABLE albums ADD COLUMN meta_ts REAL NOT NULL DEFAULT 0",
        "UPDATE albums SET uuid=lower(hex(randomblob(16))) WHERE uuid IS NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_albums_uuid ON albums(uuid)",
        "CREATE INDEX IF NOT EXISTS idx_media_meta_ts ON media(meta_ts)",
        """CREATE TABLE IF NOT EXISTS sync_tombstones(uuid TEXT PRIMARY KEY, kind TEXT NOT NULL, ts REAL NOT NULL)""",
        f"""CREATE TRIGGER IF NOT EXISTS trg_media_meta_ts AFTER UPDATE OF {SYNC_MEDIA_COLUMNS} ON media
            WHEN NEW.meta_ts = OLD.meta_ts BEGIN UPDATE media SET meta_ts={SYNC_STAMP} WHERE id=NEW.id; END""",
        f"""CREATE TRIGGER IF NOT EXISTS trg_mk_add AFTER INSERT ON media_keywords
            BEGIN UPDATE media SET meta_ts={SYNC_STAMP} WHERE id=NEW.media_id; END""",
        f"""CREATE TRIGGER IF NOT EXISTS trg_mk_del AFTER DELETE ON media_keywords
            BEGIN UPDATE media SET meta_ts={SYNC_STAMP} WHERE id=OLD.media_id; END""",
        """CREATE TRIGGER IF NOT EXISTS trg_album_uuid AFTER INSERT ON albums WHEN NEW.uuid IS NULL
            BEGIN UPDATE albums SET uuid=lower(hex(randomblob(16))) WHERE id=NEW.id; END""",
        f"""CREATE TRIGGER IF NOT EXISTS trg_album_meta_ts AFTER UPDATE OF name ON albums WHEN NEW.meta_ts = OLD.meta_ts
            BEGIN UPDATE albums SET meta_ts={SYNC_STAMP} WHERE id=NEW.id; END""",
        f"""CREATE TRIGGER IF NOT EXISTS trg_ai_add AFTER INSERT ON album_items
            BEGIN UPDATE albums SET meta_ts={SYNC_STAMP} WHERE id=NEW.album_id; END""",
        f"""CREATE TRIGGER IF NOT EXISTS trg_ai_del AFTER DELETE ON album_items
            BEGIN UPDATE albums SET meta_ts={SYNC_STAMP} WHERE id=OLD.album_id; END""",
        f"""CREATE TRIGGER IF NOT EXISTS trg_album_gone AFTER DELETE ON albums WHEN OLD.uuid IS NOT NULL
            BEGIN INSERT OR REPLACE INTO sync_tombstones(uuid, kind, ts) VALUES(OLD.uuid, 'album', {SYNC_STAMP}); END""",
    ],
    9: [
        """CREATE TABLE IF NOT EXISTS shares(
             id INTEGER PRIMARY KEY, token TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, album_id INTEGER, title TEXT NOT NULL,
             created_ts REAL NOT NULL, expires_ts REAL, password_hash TEXT,
             allow_download INTEGER NOT NULL DEFAULT 1, allow_comments INTEGER NOT NULL DEFAULT 1,
             allow_contrib INTEGER NOT NULL DEFAULT 0, include_location INTEGER NOT NULL DEFAULT 0,
             revoked INTEGER NOT NULL DEFAULT 0, views INTEGER NOT NULL DEFAULT 0, seen_ts REAL NOT NULL DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS share_items(
             share_id INTEGER NOT NULL, media_id INTEGER NOT NULL, position INTEGER NOT NULL DEFAULT 0,
             PRIMARY KEY(share_id, media_id))""",
        """CREATE TABLE IF NOT EXISTS share_activity(
             id INTEGER PRIMARY KEY, share_id INTEGER NOT NULL, media_id INTEGER, kind TEXT NOT NULL, author TEXT NOT NULL,
             text TEXT, ts REAL NOT NULL, owner INTEGER NOT NULL DEFAULT 0)""",
        "CREATE INDEX IF NOT EXISTS idx_share_activity ON share_activity(share_id, ts)",
    ],
    8: ["ALTER TABLE media ADD COLUMN lookup_state INTEGER NOT NULL DEFAULT 0", "ALTER TABLE media ADD COLUMN lookup_json TEXT"],
    7: [f"ALTER TABLE media ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
        for col in ("is_animated", "is_timelapse", "is_cinematic", "is_spatial", "is_long_exposure")],
    6: [
        """CREATE TABLE IF NOT EXISTS pets(
             id INTEGER PRIMARY KEY, name TEXT, species TEXT NOT NULL, cover_media_id INTEGER,
             centroid BLOB NOT NULL, members INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0, created_ts REAL NOT NULL)""",
        "ALTER TABLE media ADD COLUMN pet_id INTEGER",
        "CREATE INDEX IF NOT EXISTS idx_media_pet ON media(pet_id)",
        "CREATE INDEX IF NOT EXISTS idx_media_clip_state ON media(clip_state)",
    ],
    5: [f"ALTER TABLE media ADD COLUMN {col}" for col in MEDIA_V5_COLUMNS] + [
        "ALTER TABLE keywords ADD COLUMN parent_id INTEGER",
        "ALTER TABLE keywords ADD COLUMN shortcut TEXT",
        "ALTER TABLE albums ADD COLUMN folder_id INTEGER",
        "ALTER TABLE albums ADD COLUMN rules_json TEXT",
        "ALTER TABLE people ADD COLUMN kind TEXT NOT NULL DEFAULT 'person'",
        "CREATE INDEX IF NOT EXISTS idx_media_content ON media(content_id)",
        "CREATE INDEX IF NOT EXISTS idx_media_burst ON media(burst_id)",
        "CREATE INDEX IF NOT EXISTS idx_media_stack ON media(stack_id)",
        "CREATE INDEX IF NOT EXISTS idx_media_imported ON media(imported_ts DESC)",
        """CREATE TABLE IF NOT EXISTS import_batches(
             id INTEGER PRIMARY KEY, started_ts REAL NOT NULL, finished_ts REAL, source TEXT NOT NULL,
             label TEXT, imported INTEGER NOT NULL DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS album_folders(
             id INTEGER PRIMARY KEY, name TEXT NOT NULL, parent_id INTEGER, position INTEGER NOT NULL DEFAULT 0,
             created_ts REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS stacks(
             id INTEGER PRIMARY KEY, kind TEXT NOT NULL, top_media_id INTEGER, created_ts REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS clip_vectors(media_id INTEGER PRIMARY KEY, vec BLOB NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS media_labels(
             media_id INTEGER NOT NULL, label TEXT NOT NULL, kind TEXT NOT NULL, score REAL NOT NULL,
             PRIMARY KEY(media_id, label))""",
        "CREATE INDEX IF NOT EXISTS idx_labels_label ON media_labels(label)",
        """CREATE TABLE IF NOT EXISTS memories(
             id INTEGER PRIMARY KEY, kind TEXT NOT NULL, key TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
             subtitle TEXT, start_ts REAL, end_ts REAL, key_media_id INTEGER, favorite INTEGER NOT NULL DEFAULT 0,
             hidden INTEGER NOT NULL DEFAULT 0, music TEXT, created_ts REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS memory_items(
             memory_id INTEGER NOT NULL, media_id INTEGER NOT NULL, position INTEGER NOT NULL DEFAULT 0,
             PRIMARY KEY(memory_id, media_id))""",
        """CREATE TABLE IF NOT EXISTS people_groups(key TEXT PRIMARY KEY, name TEXT, hidden INTEGER NOT NULL DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS metadata_templates(
             id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, fields_json TEXT NOT NULL, created_ts REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS workflows(
             id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, steps_json TEXT NOT NULL, created_ts REAL NOT NULL)""",
    ],
    4: [
        "ALTER TABLE media ADD COLUMN live_video_id INTEGER",
        "ALTER TABLE media ADD COLUMN live_of INTEGER",
        "CREATE INDEX IF NOT EXISTS idx_media_live_of ON media(live_of)",
    ],
    3: [
        "ALTER TABLE people ADD COLUMN cover_locked INTEGER NOT NULL DEFAULT 0",
    ],
    2: [
        "ALTER TABLE media ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE media ADD COLUMN ocr_text TEXT",
        "ALTER TABLE people ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0",
    ],
}


def init_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    row = conn.execute("SELECT version FROM schema_meta").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_meta(version) VALUES (1)")
    current = row["version"] if row is not None else 1
    for target in range(current + 1, SCHEMA_VERSION + 1):
        for statement in MIGRATIONS.get(target, []):
            try:
                conn.execute(statement)
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc):
                    raise
        conn.execute("UPDATE schema_meta SET version=?", (target,))
    conn.commit()


def reset_thread_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def q(sql: str, params: Iterable[Any] = ()) -> List[sqlite3.Row]:
    return connect().execute(sql, tuple(params)).fetchall()


def q1(sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    return connect().execute(sql, tuple(params)).fetchone()


def ex(sql: str, params: Iterable[Any] = ()) -> int:
    conn = connect()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur.lastrowid or cur.rowcount


def exn(sql: str, params: Iterable[Any] = ()) -> int:
    conn = connect()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur.rowcount


def exmany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    conn = connect()
    conn.executemany(sql, [tuple(r) for r in rows])
    conn.commit()


def setting_get(key: str) -> Optional[str]:
    row = q1("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else None


def setting_set(key: str, value: str) -> None:
    ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def media_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["favorite"] = bool(d.get("favorite"))
    d["private"] = bool(d.get("private"))
    d["is_screenshot"] = bool(d.get("is_screenshot"))
    d["is_screen_rec"] = bool(d.get("is_screen_rec"))
    d["hidden"] = bool(d.get("hidden"))
    for heavy in ("exif_json", "iptc_json", "lookup_json"):
        d.pop(heavy, None)
    return d


def now() -> float:
    return time.time()
