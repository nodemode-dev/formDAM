import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from ..db import ex, q1
from . import libraryfs, renamesvc


def _unique(path: str, taken: Optional[set] = None) -> str:
    base, ext = os.path.splitext(path)
    cand, i = path, 1
    while os.path.exists(cand) or (taken is not None and cand in taken):
        cand = f"{base}-{i}{ext}"
        i += 1
    return cand


def rename_plan(ids: List[int], template: str, start: int = 1, custom: str = "") -> List[Dict[str, Any]]:
    from .. import vaultcrypt

    plan, taken = [], set()
    for n, media_id in enumerate(ids):
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        if row is None:
            continue
        _, ext = os.path.splitext(row["name"])
        new_name = renamesvc.expand(template, dict(row), start + n, custom) + ext
        entry = {"id": media_id, "old": row["name"], "new": new_name, "ok": True, "reason": ""}
        if vaultcrypt.is_vaulted(media_id) or vaultcrypt.protected(row):
            entry.update(ok=False, reason="Hidden, deleted or private items keep their names")
        else:
            src = libraryfs.abs_path(row["rel_path"])
            dest = _unique(os.path.join(os.path.dirname(src), new_name), taken)
            if os.path.normcase(dest) == os.path.normcase(src):
                entry.update(ok=False, reason="Unchanged")
            entry["new"] = os.path.basename(dest)
            taken.add(dest)
        plan.append(entry)
    return plan


def rename(ids: List[int], template: str, start: int = 1, custom: str = "") -> List[Dict[str, Any]]:
    plan = rename_plan(ids, template, start, custom)
    for entry in plan:
        if not entry["ok"]:
            continue
        row = q1("SELECT * FROM media WHERE id=?", (entry["id"],))
        src = libraryfs.abs_path(row["rel_path"])
        dest = os.path.join(os.path.dirname(src), entry["new"])
        if os.path.exists(dest):
            entry.update(ok=False, reason="Name taken")
            continue
        os.rename(src, dest)
        for side in (src + ".xmp", os.path.splitext(src)[0] + ".xmp"):
            if os.path.isfile(side):
                os.rename(side, os.path.splitext(dest)[0] + ".xmp")
                break
        rel = dest if row["referenced"] else os.path.relpath(dest, libraryfs.originals_dir())
        ex("UPDATE media SET rel_path=?, name=? WHERE id=?", (rel, entry["new"], entry["id"]))
    return plan


def copy_originals(ids: List[int], dest: str, state: Dict[str, Any]) -> None:
    from .. import vaultcrypt

    os.makedirs(dest, exist_ok=True)
    counts = {"copied": 0, "skipped": 0}
    state["counts"] = counts
    for media_id in ids:
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        if row is None or vaultcrypt.protected(row) or vaultcrypt.is_vaulted(media_id):
            counts["skipped"] += 1
            continue
        src = libraryfs.abs_path(row["rel_path"])
        if not os.path.isfile(src):
            counts["skipped"] += 1
            continue
        target = _unique(os.path.join(dest, row["name"]))
        shutil.copy2(src, target)
        counts["copied"] += 1


def _run(args: List[str]) -> bool:
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def reveal(path: str) -> bool:
    if sys.platform == "darwin":
        return _run(["open", "-R", path])
    if os.name == "nt":
        return _run(["explorer", "/select,", path])
    return _run(["xdg-open", os.path.dirname(path)])


def open_with(path: str, app: Optional[str] = None) -> bool:
    if sys.platform == "darwin":
        return _run(["open", "-a", app, path] if app else ["open", path])
    if os.name == "nt":
        if app:
            return _run([app, path])
        os.startfile(path)  # type: ignore[attr-defined]
        return True
    return _run([app, path] if app else ["xdg-open", path])


def open_url(url: str) -> bool:
    if sys.platform == "darwin":
        return _run(["open", url])
    if os.name == "nt":
        os.startfile(url)  # type: ignore[attr-defined]
        return True
    return _run(["xdg-open", url])


def editor_apps() -> List[str]:
    if sys.platform != "darwin":
        return []
    names = []
    for folder in ("/Applications", os.path.expanduser("~/Applications")):
        if not os.path.isdir(folder):
            continue
        for entry in sorted(os.listdir(folder)):
            if entry.endswith(".app"):
                names.append(entry[:-4])
    return names
