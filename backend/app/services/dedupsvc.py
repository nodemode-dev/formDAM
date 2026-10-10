import time
from typing import Any, Dict, List, Optional

from ..db import ex, exmany, q, q1
from ..dedup import visual
from . import libraryfs

PROBE_LIMIT = 3


def _entry(row) -> Optional[Dict[str, Any]]:
    path = libraryfs.abs_path(row["rel_path"])
    sig = visual.image_signature(path) if row["kind"] == "image" else visual.video_signature(path)
    if sig is None or sig.flat:
        return None
    return {
        "id": row["id"], "sig": sig, "size": row["size"], "created": row["created_ts"],
        "pixels": (sig.width or 0) * (sig.height or 0), "kind": row["kind"],
    }


def _bucket(sig) -> int:
    if not sig.width or not sig.height:
        return 0
    return round(10 * sig.width / sig.height)


def _keeper_sort(members: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(members, key=lambda m: (-m["pixels"], -m["size"], m["created"], m["id"]))


def _verified(members: List[Dict[str, Any]], threshold: int):
    ordered = _keeper_sort(members)
    keeper = ordered[0]
    kept, evicted = [keeper], []
    for member in ordered[1:]:
        sim = visual.similarity(keeper["sig"], member["sig"])
        if sim >= threshold:
            member["pair_sim"] = sim
            kept.append(member)
        else:
            evicted.append(member)
    return kept, evicted


def _cluster(entries: List[Dict[str, Any]], threshold: int) -> List[List[Dict[str, Any]]]:
    groups: Dict[Any, List[List[Dict[str, Any]]]] = {}
    for entry in entries:
        key = (entry["kind"], _bucket(entry["sig"]))
        clusters = groups.setdefault(key, [])
        placed = False
        for cluster in clusters:
            for probe in cluster[:PROBE_LIMIT]:
                if visual.similarity(probe["sig"], entry["sig"]) >= threshold:
                    cluster.append(entry)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            clusters.append([entry])
    raw = [c for clusters in groups.values() for c in clusters if len(c) > 1]
    final: List[List[Dict[str, Any]]] = []
    strays: List[Dict[str, Any]] = []
    for cluster in raw:
        kept, evicted = _verified(cluster, threshold)
        if len(kept) > 1:
            final.append(kept)
        strays.extend(evicted)
    if strays:
        retry: Dict[Any, List[List[Dict[str, Any]]]] = {}
        for entry in strays:
            key = (entry["kind"], _bucket(entry["sig"]))
            clusters = retry.setdefault(key, [])
            placed = False
            for cluster in clusters:
                if visual.similarity(cluster[0]["sig"], entry["sig"]) >= threshold:
                    cluster.append(entry)
                    placed = True
                    break
            if not placed:
                clusters.append([entry])
        for clusters in retry.values():
            for cluster in clusters:
                if len(cluster) < 2:
                    continue
                kept, _ = _verified(cluster, threshold)
                if len(kept) > 1:
                    final.append(kept)
    return final


def scan_job(state: Dict[str, Any], threshold: int, include_videos: bool = True, auto_resolve_exact: bool = False) -> None:
    threshold = max(visual.FLOOR_SIMILARITY, min(100, threshold))
    counts = {"exact_sets": 0, "visual_sets": 0, "fingerprinted": 0, "videos_skipped": 0}
    state["counts"] = counts
    ex("DELETE FROM dup_members WHERE set_id IN (SELECT id FROM dup_sets WHERE resolved_ts IS NULL)")
    ex("DELETE FROM dup_sets WHERE resolved_ts IS NULL")
    stamp = time.time()

    exact_groups = q(
        """SELECT sha256, size, COUNT(*) AS n FROM media
           WHERE trashed_ts IS NULL AND private=0 AND hidden=0 AND live_of IS NULL GROUP BY sha256, size HAVING n > 1"""
    )
    for group in exact_groups:
        rows = q(
            "SELECT id FROM media WHERE sha256=? AND size=? AND trashed_ts IS NULL AND private=0 AND hidden=0 AND live_of IS NULL ORDER BY created_ts, id",
            (group["sha256"], group["size"]),
        )
        keeper = rows[0]["id"]
        set_id = ex(
            "INSERT INTO dup_sets(job_ts, match_kind, similarity, keeper_media_id) VALUES(?,?,?,?)",
            (stamp, "exact", 100, keeper),
        )
        exmany("INSERT INTO dup_members(set_id, media_id, similarity) VALUES(?,?,?)",
               [(set_id, r["id"], 100) for r in rows[1:]])
        counts["exact_sets"] += 1

    if auto_resolve_exact:
        counts["auto_resolved"] = resolve_all_exact()["trashed"]
    has_ffmpeg = bool(visual.ffmpeg_path() and visual.ffprobe_path())
    rows = q(
        """SELECT id, rel_path, kind, size, created_ts FROM media
           WHERE trashed_ts IS NULL AND private=0 AND hidden=0 AND live_of IS NULL ORDER BY id"""
    )
    entries: List[Dict[str, Any]] = []
    for row in rows:
        if row["kind"] == "video" and (not has_ffmpeg or not include_videos):
            counts["videos_skipped"] += 1
            continue
        entry = _entry(row)
        counts["fingerprinted"] += 1
        if entry:
            entries.append(entry)

    exact_ids = {m["media_id"] for m in q("SELECT media_id FROM dup_members")}
    entries = [e for e in entries if e["id"] not in exact_ids]
    for cluster in _cluster(entries, threshold):
        keeper = cluster[0]
        weakest = min(m.get("pair_sim", 100) for m in cluster[1:])
        set_id = ex(
            "INSERT INTO dup_sets(job_ts, match_kind, similarity, keeper_media_id) VALUES(?,?,?,?)",
            (stamp, "visual", weakest, keeper["id"]),
        )
        exmany("INSERT INTO dup_members(set_id, media_id, similarity) VALUES(?,?,?)",
               [(set_id, m["id"], m.get("pair_sim", 100)) for m in cluster[1:]])
        counts["visual_sets"] += 1


def list_sets() -> List[Dict[str, Any]]:
    sets = []
    for row in q("SELECT * FROM dup_sets WHERE resolved_ts IS NULL ORDER BY match_kind DESC, id"):
        members = q(
            """SELECT dm.similarity AS pair_sim, m.* FROM dup_members dm
               JOIN media m ON m.id = dm.media_id WHERE dm.set_id=? ORDER BY dm.media_id""",
            (row["id"],),
        )
        keeper = q1("SELECT * FROM media WHERE id=?", (row["keeper_media_id"],))
        if keeper is None:
            continue
        live = [dict(m) for m in members if m["trashed_ts"] is None]
        sets.append({
            "id": row["id"], "match_kind": row["match_kind"], "similarity": row["similarity"],
            "keeper": dict(keeper),
            "members": live,
            "reclaimable": sum(m["size"] for m in live),
        })
    return [s for s in sets if s["members"]]


CARRY_MAX = ("favorite", "rating")
CARRY_FILL = ("title", "caption", "alt_text", "lat", "lon")


def carry_to_keeper(media_id: int, keeper_id: int) -> None:
    columns = {row["name"] for row in q("PRAGMA table_info(media)")}
    src = q1("SELECT * FROM media WHERE id=?", (media_id,))
    dst = q1("SELECT * FROM media WHERE id=?", (keeper_id,))
    if src is None or dst is None:
        return
    for col in CARRY_MAX:
        if col in columns and (src[col] or 0) > (dst[col] or 0):
            ex(f"UPDATE media SET {col}=? WHERE id=?", (src[col], keeper_id))
    for col in CARRY_FILL:
        if col in columns and src[col] not in (None, "") and dst[col] in (None, ""):
            ex(f"UPDATE media SET {col}=? WHERE id=?", (src[col], keeper_id))
    now_ts = time.time()
    for row in q("SELECT album_id FROM album_items WHERE media_id=?", (media_id,)):
        ex("INSERT OR IGNORE INTO album_items(album_id, media_id, position, added_ts) VALUES(?,?,0,?)", (row["album_id"], keeper_id, now_ts))
    ex("INSERT OR IGNORE INTO media_keywords(media_id, keyword_id) SELECT ?, keyword_id FROM media_keywords WHERE media_id=?", (keeper_id, media_id))
    private = q1(
        "SELECT COUNT(*) AS n FROM album_items ai JOIN albums a ON a.id=ai.album_id WHERE ai.media_id=? AND a.is_private=1",
        (keeper_id,),
    )["n"]
    if bool(private) != bool(dst["private"]):
        ex("UPDATE media SET private=? WHERE id=?", (1 if private else 0, keeper_id))
        from .. import vaultcrypt
        vaultcrypt.reconcile(keeper_id)


def resolve(set_id: int, keep_media_id: Optional[int] = None) -> Dict[str, Any]:
    row = q1("SELECT * FROM dup_sets WHERE id=?", (set_id,))
    if row is None:
        return {"trashed": 0}
    keeper = keep_media_id or row["keeper_media_id"]
    members = [m["media_id"] for m in q("SELECT media_id FROM dup_members WHERE set_id=?", (set_id,))]
    pool = set(members + [row["keeper_media_id"]])
    pool.discard(keeper)
    stamp = time.time()
    trashed = 0
    for media_id in pool:
        target = q1("SELECT trashed_ts FROM media WHERE id=?", (media_id,))
        if target and target["trashed_ts"] is None:
            carry_to_keeper(media_id, keeper)
            ex("UPDATE media SET trashed_ts=?, trash_reason=? WHERE id=?", (stamp, f"duplicate:{set_id}", media_id))
            trashed += 1
    ex("UPDATE dup_sets SET resolved_ts=?, keeper_media_id=? WHERE id=?", (stamp, keeper, set_id))
    return {"trashed": trashed}


def resolve_all_exact() -> Dict[str, Any]:
    total = 0
    for row in q("SELECT id FROM dup_sets WHERE resolved_ts IS NULL AND match_kind='exact'"):
        total += resolve(row["id"])["trashed"]
    return {"trashed": total}


def trash_member(set_id: int, media_id: int) -> Dict[str, Any]:
    member = q1("SELECT media_id FROM dup_members WHERE set_id=? AND media_id=?", (set_id, media_id))
    if member is None:
        return {"trashed": 0}
    target = q1("SELECT trashed_ts FROM media WHERE id=?", (media_id,))
    if target is None or target["trashed_ts"] is not None:
        return {"trashed": 0}
    ex("UPDATE media SET trashed_ts=?, trash_reason=? WHERE id=?", (time.time(), f"duplicate:{set_id}", media_id))
    remaining = q1(
        """SELECT COUNT(*) AS n FROM dup_members dm JOIN media m ON m.id=dm.media_id
           WHERE dm.set_id=? AND m.trashed_ts IS NULL""",
        (set_id,),
    )
    if remaining["n"] == 0:
        ex("UPDATE dup_sets SET resolved_ts=? WHERE id=?", (time.time(), set_id))
    return {"trashed": 1}
