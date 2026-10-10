import itertools
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..db import ex, q, q1

VISIBLE = "m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL"
GROUP_MIN = 3
MEMORY_MAX = 40
MEMORY_MIN = 6


def _person_sets() -> Dict[int, Tuple[int, ...]]:
    rows = q(f"""SELECT f.media_id, f.person_id FROM faces f JOIN people p ON p.id=f.person_id JOIN media m ON m.id=f.media_id
                 WHERE p.hidden=0 AND f.person_id IS NOT NULL AND {VISIBLE}""")
    sets: Dict[int, set] = defaultdict(set)
    for r in rows:
        sets[r["media_id"]].add(r["person_id"])
    return {mid: tuple(sorted(s)) for mid, s in sets.items() if len(s) >= 2}


def groups(min_items: int = GROUP_MIN) -> List[Dict[str, Any]]:
    sets = _person_sets()
    counts: Counter = Counter()
    for people in sets.values():
        for size in range(2, min(4, len(people)) + 1):
            for combo in itertools.combinations(people, size):
                counts[combo] += 1
    names = {r["id"]: r["name"] for r in q("SELECT id, name FROM people")}
    saved = {r["key"]: r for r in q("SELECT * FROM people_groups")}
    kept: List[Tuple[Tuple[int, ...], int]] = []
    for combo, n in sorted(counts.items(), key=lambda kv: (-len(kv[0]), -kv[1])):
        if n < min_items:
            continue
        if any(set(combo) < set(big) and n <= bn for big, bn in kept):
            continue
        kept.append((combo, n))
    out = []
    for combo, n in sorted(kept, key=lambda kv: -kv[1]):
        key = "-".join(str(p) for p in combo)
        row = saved.get(key)
        if row is not None and row["hidden"]:
            continue
        label = row["name"] if row is not None and row["name"] else " & ".join(names.get(p) or "Unnamed" for p in combo)
        cover = q1(f"""SELECT m.id FROM media m WHERE {VISIBLE} AND {' AND '.join('m.id IN (SELECT media_id FROM faces WHERE person_id=?)' for _ in combo)}
                       ORDER BY m.favorite DESC, m.rating DESC, m.created_ts DESC LIMIT 1""", combo)
        out.append({"key": key, "people": list(combo), "name": label, "count": n, "cover": cover["id"] if cover else None})
    return out


def _pick(rows: List[Any], limit: int = MEMORY_MAX) -> List[int]:
    seen_stacks, chosen = set(), []
    scored = []
    for r in rows:
        if r["is_screenshot"] or r["rejected"] or r["is_screen_rec"]:
            continue
        if r["stack_id"] and r["stack_id"] in seen_stacks:
            continue
        if r["stack_id"]:
            seen_stacks.add(r["stack_id"])
        score = (r["favorite"] or 0) * 3 + (r["rating"] or 0) + (1 if r["edit_json"] else 0) + (0.5 if r["kind"] == "video" else 0)
        scored.append((score, r))
    if len(scored) <= limit:
        chosen = [r for _, r in scored]
    else:
        scored.sort(key=lambda sr: sr[1]["created_ts"])
        buckets = max(1, limit)
        size = len(scored) / buckets
        for i in range(buckets):
            chunk = scored[int(i * size):int((i + 1) * size)] or scored[-1:]
            chosen.append(max(chunk, key=lambda sr: (sr[0], sr[1]["created_ts"]))[1])
    chosen.sort(key=lambda r: r["created_ts"])
    ids, last = [], None
    for r in chosen:
        if (last is not None and r["kind"] == "image" and r["created_ts"] - last["created_ts"] < 2
                and (r["width"], r["height"], r["model"]) == (last["width"], last["height"], last["model"])):
            continue
        ids.append(r["id"])
        last = r
    return ids


def _rows(where: str, params: Tuple = ()) -> List[Any]:
    return q(f"SELECT m.* FROM media m WHERE {VISIBLE} AND {where} ORDER BY m.created_ts", params)


def _upsert(kind: str, key: str, title: str, subtitle: str, ids: List[int]) -> Optional[int]:
    if len(ids) < MEMORY_MIN:
        return None
    existing = q1("SELECT id, hidden FROM memories WHERE key=?", (key,))
    ts = q1(f"SELECT MIN(created_ts) AS a, MAX(created_ts) AS b FROM media WHERE id IN ({','.join('?' * len(ids))})", ids)
    key_media = ids[len(ids) // 3]
    fav = q1(f"SELECT id FROM media WHERE id IN ({','.join('?' * len(ids))}) ORDER BY favorite DESC, rating DESC LIMIT 1", ids)
    if fav:
        key_media = fav["id"]
    if existing:
        mid = existing["id"]
        if existing["hidden"]:
            return mid
        ex("UPDATE memories SET subtitle=?, start_ts=?, end_ts=? WHERE id=?", (subtitle, ts["a"], ts["b"], mid))
        if q1("SELECT COUNT(*) AS n FROM memory_items WHERE memory_id=?", (mid,))["n"]:
            return mid
    else:
        mid = ex("""INSERT INTO memories(kind, key, title, subtitle, start_ts, end_ts, key_media_id, created_ts)
                    VALUES(?,?,?,?,?,?,?,?)""", (kind, key, title, subtitle, ts["a"], ts["b"], key_media, time.time()))
    ex("DELETE FROM memory_items WHERE memory_id=?", (mid,))
    for pos, media_id in enumerate(ids):
        ex("INSERT OR IGNORE INTO memory_items(memory_id, media_id, position) VALUES(?,?,?)", (mid, media_id, pos))
    return mid


def generate(state: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    from . import geosvc

    made: Counter = Counter()
    for trip in geosvc.trips():
        rows = _rows("m.created_ts >= ? AND m.created_ts <= ?", (trip["start_ts"], trip["end_ts"] + 1))
        start = datetime.fromtimestamp(trip["start_ts"])
        if _upsert("trip", trip["key"], trip["title"], start.strftime("%B %Y"), _pick(rows)):
            made["trip"] += 1
    today = datetime.now()
    for back in range(1, 30):
        day = today.replace(year=today.year - back) if not (today.month == 2 and today.day == 29) else today - timedelta(days=365 * back)
        start = datetime(day.year, day.month, day.day).timestamp()
        rows = _rows("m.created_ts >= ? AND m.created_ts < ?", (start - 3 * 86400, start + 4 * 86400))
        if len(rows) >= MEMORY_MIN:
            title = f"{back} Year{'s' if back > 1 else ''} Ago"
            if _upsert("on_this_day", f"otd-{day:%Y-%m-%d}", title, day.strftime("This week in %Y"), _pick(rows)):
                made["on_this_day"] += 1
    for r in q(f"""SELECT strftime('%Y-%m', m.created_ts, 'unixepoch', 'localtime') AS ym, COUNT(*) AS n FROM media m
                   WHERE {VISIBLE} GROUP BY ym HAVING n >= 30"""):
        year, month = (int(x) for x in r["ym"].split("-"))
        start = datetime(year, month, 1)
        end = datetime(year + (month == 12), month % 12 + 1, 1)
        if end > today:
            continue
        rows = _rows("m.created_ts >= ? AND m.created_ts < ?", (start.timestamp(), end.timestamp()))
        if _upsert("month", f"month-{r['ym']}", f"Best of {start:%B}", start.strftime("%Y"), _pick(rows, 30)):
            made["month"] += 1
    for p in q("""SELECT p.id, p.name, COUNT(DISTINCT f.media_id) AS n FROM people p JOIN faces f ON f.person_id=p.id
                  WHERE p.name IS NOT NULL AND p.hidden=0 GROUP BY p.id HAVING n >= 12"""):
        rows = _rows("m.id IN (SELECT media_id FROM faces WHERE person_id=?)", (p["id"],))
        years = {datetime.fromtimestamp(r["created_ts"]).year for r in rows}
        title = f"{p['name']} Over the Years" if len(years) > 1 else f"{p['name']}"
        if _upsert("person", f"person-{p['id']}", title, f"{len(rows)} photos", _pick(rows)):
            made["person"] += 1
    for pet in q("SELECT id, name, species FROM pets WHERE hidden=0 AND members >= 8"):
        rows = _rows("m.pet_id=?", (pet["id"],))
        name = pet["name"] or ("Doggo" if pet["species"] == "dog" else "Kitty")
        if _upsert("pet", f"pet-{pet['id']}", f"{name} Through the Years", pet["species"].title(), _pick(rows)):
            made["pet"] += 1
    for lab, title in (("beach", "Beach Days"), ("snow", "Snow Days"), ("food", "Foodie Moments"), ("sunset", "Sunsets"),
                       ("mountain", "In the Mountains"), ("flower", "Flowers"), ("concert", "Live Music"), ("party", "Celebrations")):
        rows = _rows("m.id IN (SELECT media_id FROM media_labels WHERE label=?)", (lab,))
        if _upsert("subject", f"subject-{lab}", title, f"{len(rows)} moments", _pick(rows)):
            made["subject"] += 1
    if state is not None:
        state["counts"] = dict(made)
    return dict(made)


def custom(ids: List[int], title: str) -> int:
    key = f"custom-{int(time.time() * 1000)}"
    mid = ex("""INSERT INTO memories(kind, key, title, subtitle, key_media_id, created_ts) VALUES('custom',?,?,?,?,?)""",
             (key, title, "", ids[0] if ids else None, time.time()))
    for pos, media_id in enumerate(ids):
        ex("INSERT OR IGNORE INTO memory_items(memory_id, media_id, position) VALUES(?,?,?)", (mid, media_id, pos))
    ts = q1(f"SELECT MIN(created_ts) AS a, MAX(created_ts) AS b FROM media WHERE id IN ({','.join('?' * len(ids))})", ids) if ids else None
    if ts:
        ex("UPDATE memories SET start_ts=?, end_ts=? WHERE id=?", (ts["a"], ts["b"], mid))
    return mid


def listing() -> List[Dict[str, Any]]:
    out = []
    for m in q("""SELECT mm.*, (SELECT COUNT(*) FROM memory_items mi JOIN media x ON x.id=mi.media_id
                                WHERE mi.memory_id=mm.id AND x.trashed_ts IS NULL AND x.private=0 AND x.hidden=0) AS n
                  FROM memories mm WHERE mm.hidden=0 ORDER BY mm.favorite DESC, COALESCE(mm.end_ts, mm.created_ts) DESC"""):
        if not m["n"]:
            continue
        item = dict(m)
        item["count"] = item.pop("n")
        item["music"] = json.loads(m["music"]) if m["music"] and m["music"].startswith("{") else m["music"]
        out.append(item)
    return out


def items(memory_id: int) -> List[int]:
    return [r["media_id"] for r in q(f"""SELECT mi.media_id FROM memory_items mi JOIN media m ON m.id=mi.media_id
                                         WHERE mi.memory_id=? AND {VISIBLE} ORDER BY mi.position""", (memory_id,))]
