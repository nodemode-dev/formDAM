from typing import Any, Dict, List, Optional, Union

from ..db import ex, q, q1


def tree() -> List[Dict[str, Any]]:
    rows = q(
        """SELECT k.id, k.name, k.parent_id, k.shortcut,
                  (SELECT COUNT(*) FROM media_keywords mk JOIN media m ON m.id=mk.media_id
                   WHERE mk.keyword_id=k.id AND m.trashed_ts IS NULL AND m.hidden=0 AND m.private=0) AS count
           FROM keywords k ORDER BY k.name COLLATE NOCASE"""
    )
    return [dict(r) for r in rows]


def ensure(name: str, parent_id: Optional[int] = None) -> Dict[str, Any]:
    clean = name.strip().strip("|")
    if "|" in clean:
        parent = None
        for part in [p.strip() for p in clean.split("|") if p.strip()]:
            parent = ensure(part, parent["id"] if parent else parent_id)
        return parent or {}
    row = q1("SELECT * FROM keywords WHERE name=? COLLATE NOCASE", (clean,))
    if row is None:
        kid = ex("INSERT INTO keywords(name, parent_id) VALUES(?,?)", (clean, parent_id))
        row = q1("SELECT * FROM keywords WHERE id=?", (kid,))
    elif parent_id is not None and row["parent_id"] is None and row["id"] != parent_id:
        ex("UPDATE keywords SET parent_id=? WHERE id=?", (parent_id, row["id"]))
        row = q1("SELECT * FROM keywords WHERE id=?", (row["id"],))
    return dict(row)


def _ancestors(keyword_id: int) -> List[int]:
    out, cur, seen = [], keyword_id, set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        row = q1("SELECT parent_id FROM keywords WHERE id=?", (cur,))
        cur = row["parent_id"] if row else None
        if cur is not None:
            out.append(cur)
    return out


def update(keyword_id: int, name: Optional[str], parent_id: Optional[int], detach: bool, shortcut: Optional[str]) -> Dict[str, Any]:
    row = q1("SELECT * FROM keywords WHERE id=?", (keyword_id,))
    if row is None:
        raise ValueError("No such keyword")
    if name is not None and name.strip() != row["name"]:
        clash = q1("SELECT id FROM keywords WHERE name=? COLLATE NOCASE AND id<>?", (name.strip(), keyword_id))
        if clash:
            raise ValueError("Another keyword already has that name; merge them instead")
        ex("UPDATE keywords SET name=? WHERE id=?", (name.strip(), keyword_id))
    if detach:
        ex("UPDATE keywords SET parent_id=NULL WHERE id=?", (keyword_id,))
    elif parent_id is not None:
        if parent_id == keyword_id or keyword_id in _ancestors(parent_id):
            raise ValueError("A keyword cannot go inside itself")
        ex("UPDATE keywords SET parent_id=? WHERE id=?", (parent_id, keyword_id))
    if shortcut is not None:
        key = shortcut.strip().lower() or None
        if key:
            ex("UPDATE keywords SET shortcut=NULL WHERE shortcut=?", (key,))
        ex("UPDATE keywords SET shortcut=? WHERE id=?", (key, keyword_id))
    ex("UPDATE media SET xmp_ts=NULL WHERE id IN (SELECT media_id FROM media_keywords WHERE keyword_id=?)", (keyword_id,))
    return dict(q1("SELECT * FROM keywords WHERE id=?", (keyword_id,)))


def delete(keyword_id: int) -> int:
    row = q1("SELECT * FROM keywords WHERE id=?", (keyword_id,))
    if row is None:
        return 0
    ex("UPDATE keywords SET parent_id=? WHERE parent_id=?", (row["parent_id"], keyword_id))
    ex("UPDATE media SET xmp_ts=NULL WHERE id IN (SELECT media_id FROM media_keywords WHERE keyword_id=?)", (keyword_id,))
    n = q1("SELECT COUNT(*) AS n FROM media_keywords WHERE keyword_id=?", (keyword_id,))["n"]
    ex("DELETE FROM media_keywords WHERE keyword_id=?", (keyword_id,))
    ex("DELETE FROM keywords WHERE id=?", (keyword_id,))
    return n


def merge(into_id: int, from_ids: List[int]) -> int:
    moved = 0
    for kid in from_ids:
        if kid == into_id:
            continue
        moved += q1("SELECT COUNT(*) AS n FROM media_keywords WHERE keyword_id=?", (kid,))["n"]
        ex("INSERT OR IGNORE INTO media_keywords(media_id, keyword_id) SELECT media_id, ? FROM media_keywords WHERE keyword_id=?", (into_id, kid))
        ex("UPDATE keywords SET parent_id=? WHERE parent_id=?", (into_id, kid))
        ex("DELETE FROM media_keywords WHERE keyword_id=?", (kid,))
        ex("DELETE FROM keywords WHERE id=?", (kid,))
    ex("UPDATE media SET xmp_ts=NULL WHERE id IN (SELECT media_id FROM media_keywords WHERE keyword_id=?)", (into_id,))
    return moved


def assign(ids: List[int], add: List[Union[int, str]], remove: List[int]) -> Dict[str, Any]:
    added_ids = []
    for item in add:
        if isinstance(item, int) or (isinstance(item, str) and item.isdigit()):
            row = q1("SELECT id FROM keywords WHERE id=?", (int(item),))
            if row:
                added_ids.append(row["id"])
        elif str(item).strip():
            added_ids.append(ensure(str(item))["id"])
    for media_id in ids:
        for kid in added_ids:
            ex("INSERT OR IGNORE INTO media_keywords(media_id, keyword_id) VALUES(?,?)", (media_id, kid))
        for kid in remove:
            ex("DELETE FROM media_keywords WHERE media_id=? AND keyword_id=?", (media_id, kid))
        ex("UPDATE media SET xmp_ts=NULL WHERE id=?", (media_id,))
    return {"added": added_ids, "removed": remove}


def paths_for(media_id: int) -> List[str]:
    out = []
    for row in q("SELECT keyword_id FROM media_keywords WHERE media_id=?", (media_id,)):
        names, cur, seen = [], row["keyword_id"], set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            k = q1("SELECT name, parent_id FROM keywords WHERE id=?", (cur,))
            if k is None:
                break
            names.append(k["name"])
            cur = k["parent_id"]
        out.append("|".join(reversed(names)))
    return sorted(out)


def export_text() -> str:
    rows = q("SELECT id, name, parent_id FROM keywords ORDER BY name COLLATE NOCASE")
    children: Dict[Optional[int], List[Any]] = {}
    for row in rows:
        children.setdefault(row["parent_id"], []).append(row)
    lines: List[str] = []

    def walk(parent: Optional[int], depth: int, seen: set) -> None:
        for row in children.get(parent, []):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            lines.append("\t" * depth + row["name"])
            walk(row["id"], depth + 1, seen)

    walk(None, 0, set())
    return "\n".join(lines) + ("\n" if lines else "")


def import_text(text: str, replace: bool = False) -> int:
    if replace:
        ex("DELETE FROM keywords WHERE id NOT IN (SELECT keyword_id FROM media_keywords)")
    stack: List[int] = []
    created = 0
    before = q1("SELECT COUNT(*) AS n FROM keywords")["n"]
    for raw in text.splitlines():
        if not raw.strip():
            continue
        depth = len(raw) - len(raw.lstrip("\t"))
        name = raw.strip().strip("[]{}")
        del stack[depth:]
        parent = stack[-1] if stack else None
        kid = ensure(name, parent)["id"]
        stack.append(kid)
    created = q1("SELECT COUNT(*) AS n FROM keywords")["n"] - before
    return max(0, created)
