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
    if conn is not None:
        return conn
    os.makedirs(library_root(), exist_ok=True)
    _adopt_legacy_catalog()
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    _local.conn = conn
    return conn


SCHEMA_VERSION = 4

MIGRATIONS = {
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
    return d


def now() -> float:
    return time.time()
