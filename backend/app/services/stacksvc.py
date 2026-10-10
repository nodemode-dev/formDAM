import time
from typing import Any, Dict, List, Optional

from ..db import ex, q, q1


def create(ids: List[int], top_id: Optional[int], kind: str) -> int:
    ids = [i for i in dict.fromkeys(ids) if q1("SELECT id FROM media WHERE id=?", (i,))]
    if len(ids) < 2:
        return 0
    for old in {r["stack_id"] for r in q(f"SELECT stack_id FROM media WHERE id IN ({','.join('?' * len(ids))}) AND stack_id IS NOT NULL", ids)}:
        dissolve(old)
    top = top_id if top_id in ids else best_of(ids)
    stack_id = ex("INSERT INTO stacks(kind, top_media_id, created_ts) VALUES(?,?,?)", (kind, top, time.time()))
    for media_id in ids:
        ex("UPDATE media SET stack_id=? WHERE id=?", (stack_id, media_id))
    return stack_id


def best_of(ids: List[int]) -> int:
    marks = ",".join("?" * len(ids))
    row = q1(f"""SELECT id FROM media WHERE id IN ({marks})
                ORDER BY favorite DESC, rating DESC, rejected ASC, created_ts ASC, id ASC LIMIT 1""", ids)
    return row["id"] if row else ids[0]


def dissolve(stack_id: int) -> None:
    ex("UPDATE media SET stack_id=NULL WHERE stack_id=?", (stack_id,))
    ex("DELETE FROM stacks WHERE id=?", (stack_id,))


def remove(stack_id: int, ids: List[int]) -> None:
    for media_id in ids:
        ex("UPDATE media SET stack_id=NULL WHERE id=? AND stack_id=?", (media_id, stack_id))
    left = [r["id"] for r in q("SELECT id FROM media WHERE stack_id=?", (stack_id,))]
    if len(left) < 2:
        dissolve(stack_id)
        return
    top = q1("SELECT top_media_id FROM stacks WHERE id=?", (stack_id,))
    if top and top["top_media_id"] not in left:
        ex("UPDATE stacks SET top_media_id=? WHERE id=?", (best_of(left), stack_id))


def stack_burst(burst_id: str) -> Optional[int]:
    rows = q("SELECT id, stack_id FROM media WHERE burst_id=? AND trashed_ts IS NULL ORDER BY created_ts, id", (burst_id,))
    if len(rows) < 2:
        return None
    existing = {r["stack_id"] for r in rows if r["stack_id"]}
    burst_stack = None
    for sid in existing:
        if q1("SELECT kind FROM stacks WHERE id=?", (sid,))["kind"] == "burst":
            burst_stack = sid
    if burst_stack is None:
        return create([r["id"] for r in rows], None, "burst")
    for r in rows:
        if r["stack_id"] is None:
            ex("UPDATE media SET stack_id=? WHERE id=?", (burst_stack, r["id"]))
    return burst_stack


def auto(window_s: float = 0.0) -> Dict[str, Any]:
    made = 0
    for row in q("SELECT DISTINCT burst_id FROM media WHERE burst_id IS NOT NULL AND trashed_ts IS NULL"):
        if stack_burst(row["burst_id"]):
            made += 1
    if window_s > 0:
        rows = q("""SELECT id, created_ts FROM media WHERE kind='image' AND stack_id IS NULL AND trashed_ts IS NULL
                    AND hidden=0 AND private=0 ORDER BY created_ts, id""")
        group: List[Any] = []
        for row in rows:
            if group and row["created_ts"] - group[-1]["created_ts"] > window_s:
                if len(group) >= 2:
                    create([g["id"] for g in group], None, "time")
                    made += 1
                group = []
            group.append(row)
        if len(group) >= 2:
            create([g["id"] for g in group], None, "time")
            made += 1
    return {"stacks": made}


def on_metadata(media_id: int, meta: Dict[str, Any]) -> None:
    if meta.get("burst_id"):
        stack_burst(meta["burst_id"])
