import os
import tempfile
import shutil
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, File, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .. import jobs
from ..db import setting_get, setting_set
from ..security import shell_allowed
from ..services import followon, idevicesvc, libraryfs, thumbs

router = APIRouter()


class ImportIn(BaseModel):
    path: str
    move: bool = False
    reference: bool = False
    paths: Optional[List[str]] = None



@router.post("/import", status_code=202)
def start_import(body: ImportIn):
    raw = body.paths if body.paths else [body.path]
    targets = [os.path.abspath(os.path.expanduser(p)) for p in raw if p]
    targets = [t for t in targets if os.path.exists(t)]
    if not targets:
        raise HTTPException(404, detail="That path does not exist. Check for typos.")

    def run(state: Dict[str, Any]) -> None:
        counts = {"found": 0, "imported": 0, "duplicates": 0, "skipped": 0, "failed": 0}
        state["counts"] = counts
        files = []
        for target in targets:
            files.extend(libraryfs.gather_media(target))
        counts["found"] = len(files)
        libraryfs.begin_batch("folder", ", ".join(os.path.basename(t.rstrip(os.sep)) or t for t in targets))
        for path in files:
            try:
                result = libraryfs.import_one(path, move=body.move and not body.reference, reference=body.reference)
            except Exception:
                counts["failed"] += 1
                continue
            status = result["status"]
            if status == "imported":
                counts["imported"] += 1
                if result.get("kind") == "video" and result.get("id"):
                    try:
                        thumbs.ensure_thumb(result["id"], result["rel_path"], "video", 384)
                    except Exception:
                        pass
            elif status == "duplicate":
                counts["duplicates"] += 1
            else:
                counts["skipped"] += 1
        libraryfs.end_batch()
        followon.start_after_import(counts)

    return {"job_id": jobs.start("import", run)}


UPLOAD_EXTS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tif", ".tiff", ".bmp",
    ".dng", ".mov", ".mp4", ".m4v", ".webm", ".mkv", ".3gp", ".avi", ".avif", ".mts",
    ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf", ".rw2", ".rwl", ".pef",
    ".srw", ".x3f", ".3fr", ".iiq", ".erf", ".kdc", ".dcr", ".mos", ".mrw",
}


@router.post("/import/upload")
def import_upload(files: List[UploadFile] = File(...)):
    counts = {"imported": 0, "duplicates": 0, "skipped": 0, "failed": 0}
    imported: List[Dict[str, Any]] = []
    libraryfs.begin_batch("drop", f"{len(files)} dropped")
    with tempfile.TemporaryDirectory(prefix="dam-drop-") as tmp:
        for upload in files:
            name = os.path.basename(upload.filename or "dropped")
            if os.path.splitext(name)[1].lower() not in UPLOAD_EXTS:
                counts["skipped"] += 1
                continue
            local = os.path.join(tmp, name)
            try:
                with open(local, "wb") as handle:
                    shutil.copyfileobj(upload.file, handle)
                result = libraryfs.import_one(local, move=True)
            except Exception:
                counts["failed"] += 1
                continue
            status = result.get("status")
            if status == "imported":
                counts["imported"] += 1
                imported.append(result)
                if result.get("kind") == "video" and result.get("id"):
                    try:
                        thumbs.ensure_thumb(result["id"], result["rel_path"], "video", 384)
                    except Exception:
                        pass
            elif status == "duplicate":
                counts["duplicates"] += 1
                imported.append({"id": result.get("media_id")})
            else:
                counts["skipped"] += 1
    libraryfs.end_batch()
    followon.start_after_import(counts)
    return {"counts": counts, "ids": [r["id"] for r in imported if r.get("id")]}


class GlassDiagIn(BaseModel):
    diag: str


@router.post("/internal/shell/glass")
def shell_glass(body: GlassDiagIn, request: Request):
    if not shell_allowed(request):
        raise HTTPException(403, detail="Only the formDAM desktop shell may call this")
    setting_set("glass_diag", body.diag[:400])
    return {"ok": True}


@router.get("/system/glass")
def get_glass():
    return {"diag": setting_get("glass_diag") or ""}


class WindowIn(BaseModel):
    blur: int | None = None
    clear: bool | None = None
    ready: bool | None = None


@router.post("/system/window")
def set_window(body: WindowIn):
    out = {}
    if body.blur is not None:
        blur = max(0, min(64, int(body.blur)))
        print(f"FORMDAM-CTRL WINBLUR {blur}", flush=True)
        out["blur"] = blur
    if body.clear:
        print("FORMDAM-CTRL WINCLEAR 1", flush=True)
        out["clear"] = True
    if body.ready:
        print("FORMDAM-CTRL WINSHOW 1", flush=True)
        out["ready"] = True
    return out or {"ok": True}


class MenubarIn(BaseModel):
    enabled: bool


@router.post("/system/menubar")
def set_menubar(body: MenubarIn):
    setting_set("menubar_enabled", "1" if body.enabled else "0")
    print(f"FORMDAM-CTRL TRAYSET {1 if body.enabled else 0}", flush=True)
    return {"enabled": body.enabled}


@router.get("/system/menubar")
def get_menubar():
    return {"enabled": setting_get("menubar_enabled") == "1"}


@router.get("/idevice/status")
def idevice_status():
    return idevicesvc.status_detail()


@router.get("/idevice/devices")
def idevice_devices():
    if not idevicesvc.supported():
        return {"devices": []}
    try:
        return {"devices": idevicesvc.list_devices()}
    except Exception as exc:
        raise HTTPException(500, detail=f"Device listing failed: {type(exc).__name__}") from exc


class IDeviceImportIn(BaseModel):
    serial: str
    keys: Optional[List[int]] = None
    gen: Optional[int] = None
    delete_after: bool = False


@router.post("/idevice/import")
def idevice_import(body: IDeviceImportIn):
    if not idevicesvc.supported():
        raise HTTPException(501, detail="iPhone import needs the formDAM macOS desktop app")

    def run(state: Dict[str, Any]) -> None:
        libraryfs.begin_batch("iphone", body.serial)
        try:
            idevicesvc.run_import(body.serial, state, keys=body.keys, gen=body.gen, delete_after=body.delete_after)
        finally:
            libraryfs.end_batch()
        followon.start_after_import(state.get("counts") or {})

    return {"job_id": jobs.start("idevice-import", run)}


class IDeviceSerialIn(BaseModel):
    serial: str


@router.post("/idevice/contents")
def idevice_contents(body: IDeviceSerialIn):
    try:
        return idevicesvc.contents(body.serial)
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.get("/idevice/thumb")
def idevice_thumb(serial: str, key: int, gen: int):
    data = idevicesvc.device_thumb(serial, key, gen)
    if not data:
        raise HTTPException(404, detail="No thumbnail")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/idevice/session/close")
def idevice_close(body: IDeviceSerialIn):
    if jobs.running("idevice-import"):
        return {"ok": True, "deferred": True}
    idevicesvc.close_device(body.serial)
    return {"ok": True}
