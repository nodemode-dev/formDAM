import hashlib
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .. import jobs, libraries
from ..config import cache_dir, library_root, originals_dir
from ..db import ex, init_db, q, q1, setting_get, setting_set
from ..services import classify, decode, libraryfs, thumbs

router = APIRouter()

WEB_NATIVE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp"}


class SwitchIn(BaseModel):
    path: str = Field(..., min_length=1, max_length=2000)
    create: bool = False
    name: Optional[str] = Field(None, max_length=120)


class RepairIn(BaseModel):
    deep: bool = False


class ConsolidateIn(BaseModel):
    ids: List[int] = Field(default_factory=list, max_length=100000)
    move: bool = False


class ForgetIn(BaseModel):
    path: str


@router.get("/library")
def library_info():
    root = library_root()
    stats = q1("""SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes, COALESCE(SUM(referenced),0) AS refs FROM media WHERE trashed_ts IS NULL""")
    return {"path": root, "name": os.path.basename(root.rstrip(os.sep)) or root, "items": stats["n"], "bytes": stats["bytes"],
            "referenced": stats["refs"], "libraries": libraries.listing(), "repair": json.loads(setting_get("repair_report") or "null")}


def _reset_caches() -> None:
    try:
        from ..services import clipsvc

        clipsvc._matrix = None
        clipsvc._search_cache.clear()
        clipsvc.mark_dirty()
    except Exception:
        pass
    try:
        from . import edit

        edit._bases.clear()
    except Exception:
        pass


@router.post("/library/switch")
def switch_library(body: SwitchIn):
    busy = sorted(set(jobs.any_running()))
    if busy:
        raise HTTPException(409, detail=f"Wait for {', '.join(busy)} to finish before switching libraries")
    path = os.path.abspath(os.path.expanduser(body.path))
    exists = os.path.isfile(os.path.join(path, "dam.db")) or os.path.isfile(os.path.join(path, "damp.db"))
    if not exists and not body.create:
        raise HTTPException(404, detail="No formDAM library at that path; choose New Library to create one there")
    if not exists and os.path.isdir(path) and any(not n.startswith(".") for n in os.listdir(path)):
        path = os.path.join(path, (body.name or "formDAM Library").strip() or "formDAM Library")
    os.makedirs(path, exist_ok=True)
    os.environ["FORMDAM_LIBRARY"] = path
    init_db()
    os.makedirs(originals_dir(), exist_ok=True)
    os.makedirs(cache_dir(), exist_ok=True)
    from .. import vaultcrypt

    vaultcrypt.startup()
    _reset_caches()
    libraries.remember(path, body.name)
    from . import browse, curate, discover, geo

    for kick in (browse.ensure_backfill, geo.ensure_geo_backfill, discover.ensure_clip, curate.ensure_memories):
        try:
            kick()
        except Exception:
            pass
    return library_info()


@router.post("/library/forget")
def forget_library(body: ForgetIn):
    if os.path.abspath(body.path) == os.path.abspath(library_root()):
        raise HTTPException(409, detail="Switch to another library before removing this one from the list")
    libraries.forget(body.path)
    return {"libraries": libraries.listing()}


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def repair_job(deep: bool, state: Dict[str, Any]) -> None:
    from .. import vaultcrypt
    from ..db import connect

    counts: Dict[str, Any] = {"checked": 0, "missing": 0, "offline": 0, "thumbs_rebuilt": 0, "orphans": 0, "cache_freed": 0, "mismatched": 0}
    state["counts"] = counts
    report: Dict[str, Any] = {"started": time.time(), "deep": deep, "missing": [], "offline": [], "orphans": [], "mismatched": []}
    integrity = connect().execute("PRAGMA integrity_check").fetchone()[0]
    report["integrity"] = integrity
    known = set()
    for row in q("SELECT id, rel_path, kind, sha256, referenced, name FROM media WHERE trashed_ts IS NULL"):
        counts["checked"] += 1
        if vaultcrypt.is_vaulted(row["id"]):
            continue
        path = libraryfs.abs_path(row["rel_path"])
        if not row["referenced"]:
            known.add(os.path.normcase(os.path.abspath(path)))
        if not os.path.isfile(path):
            key = "offline" if row["referenced"] else "missing"
            counts[key] += 1
            if len(report[key]) < 200:
                report[key].append({"id": row["id"], "name": row["name"], "path": path})
            continue
        if not os.path.isfile(thumbs.thumb_path(row["id"], 384)):
            if thumbs.ensure_thumb(row["id"], row["rel_path"], row["kind"], 384):
                counts["thumbs_rebuilt"] += 1
        if deep and row["sha256"] and _sha(path) != row["sha256"]:
            counts["mismatched"] += 1
            if len(report["mismatched"]) < 200:
                report["mismatched"].append({"id": row["id"], "name": row["name"]})
    base = originals_dir()
    for folder, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            if name.startswith(".") or name.lower().endswith((".xmp", ".tmp", ".part")):
                continue
            full = os.path.normcase(os.path.abspath(os.path.join(folder, name)))
            if full not in known and classify.media_kind(name)[0]:
                counts["orphans"] += 1
                if len(report["orphans"]) < 200:
                    report["orphans"].append(full)
    ids = {r["id"] for r in q("SELECT id FROM media")}
    for sub in ("thumbs", "render"):
        folder = os.path.join(cache_dir(), sub)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            head = name.split("_", 1)[0]
            if head.isdigit() and int(head) not in ids:
                try:
                    os.unlink(os.path.join(folder, name))
                    counts["cache_freed"] += 1
                except OSError:
                    pass
    connect().execute("PRAGMA optimize")
    report["finished"] = time.time()
    report["counts"] = counts
    setting_set("repair_report", json.dumps(report))


@router.post("/library/repair", status_code=202)
def repair(body: RepairIn):
    running = jobs.running("repair")
    if running:
        return {"job_id": running["id"]}
    deep = body.deep
    return {"job_id": jobs.start("repair", lambda state: repair_job(deep, state))}


@router.post("/library/import-orphans", status_code=202)
def import_orphans():
    report = json.loads(setting_get("repair_report") or "{}")
    orphans = [p for p in report.get("orphans") or [] if os.path.isfile(p)]

    def run(state: Dict[str, Any]) -> None:
        counts = {"imported": 0, "duplicates": 0}
        state["counts"] = counts
        for path in orphans:
            result = libraryfs.import_one(path, move=True)
            counts["imported" if result.get("status") == "imported" else "duplicates"] += 1

    return {"job_id": jobs.start("import", run)}


@router.post("/library/consolidate", status_code=202)
def consolidate(body: ConsolidateIn):
    ids = body.ids or [r["id"] for r in q("SELECT id FROM media WHERE referenced=1 AND trashed_ts IS NULL")]
    move = body.move

    def run(state: Dict[str, Any]) -> None:
        counts = {"copied": 0, "offline": 0}
        state["counts"] = counts
        for media_id in ids:
            row = libraryfs.consolidate(media_id, move=move)
            counts["copied" if row is not None else "offline"] += 1

    return {"job_id": jobs.start("consolidate", run)}


def _shortcuts() -> List[Dict[str, str]]:
    home = os.path.expanduser("~")
    out = [{"name": "Home", "path": home}]
    for sub in ("Pictures", "Desktop", "Downloads", "Documents", "Movies"):
        p = os.path.join(home, sub)
        if os.path.isdir(p):
            out.append({"name": sub, "path": p})
    if sys.platform == "darwin" and os.path.isdir("/Volumes"):
        out += [{"name": v, "path": os.path.join("/Volumes", v)} for v in sorted(os.listdir("/Volumes")) if not v.startswith(".")]
    return out


@router.get("/disk/browse")
def browse_disk(path: str = Query("", max_length=4000)):
    target = os.path.abspath(os.path.expanduser(path or "~"))
    if not os.path.isdir(target):
        raise HTTPException(404, detail="That folder does not exist")
    dirs, files = [], []
    try:
        entries = sorted(os.scandir(target), key=lambda e: e.name.lower())
    except PermissionError:
        raise HTTPException(403, detail="formDAM cannot read that folder") from None
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                dirs.append({"name": entry.name, "path": entry.path})
                continue
            kind, _ = classify.media_kind(entry.name)
            if not kind:
                continue
            st = entry.stat()
        except OSError:
            continue
        files.append({"name": entry.name, "path": entry.path, "size": st.st_size, "mtime": st.st_mtime, "kind": kind})
    for f in files[:2000]:
        hit = q1("SELECT id FROM media WHERE rel_path=? OR (name=? AND size=?) LIMIT 1", (f["path"], f["name"], f["size"]))
        f["media_id"] = hit["id"] if hit else None
        side = _sidecar_record(f["path"])
        f["rating"] = side.get("rating", 0)
        f["label"] = str(side.get("label") or "").lower()
    parent = os.path.dirname(target) if os.path.dirname(target) != target else None
    return {"path": target, "parent": parent, "dirs": dirs, "files": files, "shortcuts": _shortcuts(), "sidecars": sum(1 for e in entries if e.name.lower().endswith(".xmp"))}


class DiskMetaIn(BaseModel):
    paths: List[str] = Field(..., min_length=1, max_length=5000)
    rating: Optional[int] = Field(None, ge=-1, le=5)
    label: Optional[str] = Field(None, max_length=20)
    keywords: List[str] = Field(default_factory=list, max_length=50)


def _sidecar_record(path: str) -> Dict[str, Any]:
    from ..services import xmpsvc

    side = xmpsvc.find_sidecar(path)
    if not side:
        return {}
    try:
        with open(side, "r", encoding="utf-8", errors="replace") as fh:
            return xmpsvc.parse_xmp(fh.read())
    except OSError:
        return {}


@router.post("/disk/meta")
def disk_meta(body: DiskMetaIn):
    from ..services import xmpsvc

    written = 0
    for raw in body.paths:
        path = _media_file(raw)
        rec = _sidecar_record(path)
        rec.setdefault("meta", {})
        if body.rating is not None:
            rec["rating"] = body.rating
        if body.label is not None:
            rec["label"] = body.label
        if body.keywords:
            rec["keywords"] = sorted(set(rec.get("keywords") or []) | set(body.keywords))
        side = xmpsvc.find_sidecar(path) or xmpsvc.sidecar_for(path)
        tmp = side + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(xmpsvc.build_xmp(rec))
        os.replace(tmp, side)
        hit = q1("SELECT id FROM media WHERE rel_path=?", (path,))
        if hit:
            xmpsvc.apply_record(hit["id"], {k: v for k, v in rec.items() if k in ("rating", "label", "keywords")})
            if body.label == "":
                ex("UPDATE media SET label=NULL WHERE id=?", (hit["id"],))
        written += 1
    return {"written": written}


def _media_file(path: str) -> str:
    full = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(full) or not classify.media_kind(os.path.basename(full))[0]:
        raise HTTPException(404, detail="Not a media file")
    return full


@router.get("/disk/thumb")
def disk_thumb(path: str = Query(..., max_length=4000), s: int = Query(384, ge=64, le=2048)):
    full = _media_file(path)
    st = os.stat(full)
    key = hashlib.sha1(f"{full}|{st.st_mtime}|{st.st_size}|{s}".encode()).hexdigest()
    folder = os.path.join(cache_dir(), "fsthumbs")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, f"{key}.webp")
    if not os.path.isfile(out):
        kind, _ = classify.media_kind(os.path.basename(full))
        img = None
        if kind == "image":
            img = decode.open_image(full, os.path.basename(full), max_long=s)
        else:
            from ..dedup.visual import ffmpeg_path
            import subprocess

            binary = ffmpeg_path()
            if binary:
                frame = os.path.join(folder, f"{key}.jpg")
                subprocess.run([binary, "-hide_banner", "-loglevel", "error", "-y", "-ss", "1", "-i", full, "-frames:v", "1",
                                "-vf", f"scale={s}:{s}:force_original_aspect_ratio=decrease", frame], capture_output=True, timeout=60)
                if os.path.isfile(frame):
                    from PIL import Image

                    img = Image.open(frame)
                    img.load()
                    os.unlink(frame)
        if img is None:
            raise HTTPException(415, detail="No preview for this file")
        img.convert("RGB").save(out, "WEBP", quality=80)
    return FileResponse(out, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/disk/file")
def disk_file(path: str = Query(..., max_length=4000)):
    full = _media_file(path)
    ext = os.path.splitext(full)[1].lower()
    kind, mime = classify.media_kind(os.path.basename(full))
    if kind == "video" or ext in WEB_NATIVE:
        return FileResponse(full, media_type=mime or "application/octet-stream", headers={"Cache-Control": "no-store"})
    img = decode.open_image(full, os.path.basename(full), max_long=3072, develop=True)
    if img is None:
        raise HTTPException(415, detail="This file could not be decoded")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "WEBP", quality=88)
    return Response(buf.getvalue(), media_type="image/webp", headers={"Cache-Control": "no-store"})
