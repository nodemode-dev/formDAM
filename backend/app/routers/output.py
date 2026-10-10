import json
import os
import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import jobs
from ..db import ex, q, q1, setting_get, setting_set
from ..services import outputsvc, xmpsvc
from .guard import ensure_visible

router = APIRouter()
MAX_IDS = 20000


class IdsIn(BaseModel):
    ids: List[int] = Field(default_factory=list, max_length=MAX_IDS)


class FieldsIn(BaseModel):
    ids: List[int] = Field(..., max_length=MAX_IDS)
    fields: Dict[str, Any]
    mode: str = Field("replace", pattern="^(replace|fill)$")


class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    fields: Dict[str, Any]


class ExportIn(BaseModel):
    ids: List[int] = Field(..., max_length=MAX_IDS)
    dest: str = Field(..., min_length=1, max_length=2000)
    options: Dict[str, Any] = {}


class SheetIn(BaseModel):
    ids: List[int] = Field(..., max_length=2000)
    options: Dict[str, Any] = {}


class WorkflowIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    steps: List[Dict[str, Any]]


class XmpSettingsIn(BaseModel):
    auto: bool


def _check(ids: List[int], request: Request) -> None:
    for media_id in ids:
        ensure_visible(q1("SELECT * FROM media WHERE id=?", (media_id,)), request)


def _fields_of(row) -> Dict[str, Any]:
    out = xmpsvc.iptc_of(row)
    out.update({"title": row["title"] or "", "caption": row["caption"] or "", "altText": row["alt_text"] or ""})
    return out


@router.post("/fileinfo/common")
def common_fields(body: IdsIn, request: Request):
    _check(body.ids[:500], request)
    merged: Dict[str, Any] = {}
    mixed: List[str] = []
    for i, media_id in enumerate(body.ids[:500]):
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        if row is None:
            continue
        fields = _fields_of(row)
        keys = set(fields) | set(merged)
        for key in keys:
            value = fields.get(key, "")
            if i == 0:
                merged[key] = value
            elif merged.get(key, "") != value and key not in mixed:
                mixed.append(key)
    place = None
    if len(body.ids) == 1:
        row = q1("SELECT place, admin, country FROM media WHERE id=?", (body.ids[0],))
        place = dict(row) if row else None
    for key in mixed:
        merged[key] = ""
    return {"fields": merged, "mixed": mixed, "place": place, "known": xmpsvc.FIELDS + ["title", "caption", "altText"]}


@router.post("/fileinfo")
def save_fields(body: FieldsIn, request: Request):
    _check(body.ids, request)
    allowed = set(xmpsvc.FIELDS) | {"title", "caption", "altText"}
    fields = {k: (str(v)[:4000] if v is not None else None) for k, v in body.fields.items() if k in allowed}
    return {"changed": outputsvc.apply_fields(body.ids, fields, body.mode)}


@router.get("/metadata-templates")
def templates():
    return {"templates": [{"id": r["id"], "name": r["name"], "fields": json.loads(r["fields_json"])}
                          for r in q("SELECT * FROM metadata_templates ORDER BY name COLLATE NOCASE")]}


@router.post("/metadata-templates", status_code=201)
def create_template(body: TemplateIn):
    existing = q1("SELECT id FROM metadata_templates WHERE name=?", (body.name.strip(),))
    if existing:
        ex("UPDATE metadata_templates SET fields_json=? WHERE id=?", (json.dumps(body.fields), existing["id"]))
        return {"id": existing["id"]}
    return {"id": ex("INSERT INTO metadata_templates(name, fields_json, created_ts) VALUES(?,?,?)",
                     (body.name.strip(), json.dumps(body.fields), time.time()))}


@router.delete("/metadata-templates/{template_id}")
def delete_template(template_id: int):
    ex("DELETE FROM metadata_templates WHERE id=?", (template_id,))
    return {"ok": True}


@router.get("/xmp/settings")
def xmp_settings():
    return {"auto": setting_get("xmp_auto") == "1", "pending": xmpsvc.pending()}


@router.put("/xmp/settings")
def set_xmp_settings(body: XmpSettingsIn):
    setting_set("xmp_auto", "1" if body.auto else "0")
    if body.auto:
        ensure_sidecars()
    return {"auto": body.auto}


def ensure_sidecars() -> None:
    if setting_get("xmp_auto") == "1" and xmpsvc.pending() and not jobs.running("xmp"):
        jobs.start("xmp", xmpsvc.sidecar_job)


_ticker: Dict[str, Any] = {}


def start_autosave(interval: float = 30.0) -> None:
    if _ticker.get("thread"):
        return
    import threading

    from ..db import reset_thread_conn

    def loop() -> None:
        reset_thread_conn()
        while True:
            time.sleep(interval)
            try:
                ensure_sidecars()
            except Exception:
                pass

    _ticker["thread"] = threading.Thread(target=loop, name="xmp-autosave", daemon=True)
    _ticker["thread"].start()


@router.post("/xmp/write", status_code=202)
def write_sidecars(body: IdsIn, request: Request):
    _check(body.ids, request)
    ids = list(body.ids)

    def run(state: Dict[str, Any]) -> None:
        counts = {"written": 0, "skipped": 0}
        state["counts"] = counts
        for media_id in ids:
            counts["written" if xmpsvc.write_sidecar(media_id) else "skipped"] += 1

    return {"job_id": jobs.start("xmp", run)}


@router.post("/xmp/read")
def read_sidecars(body: IdsIn, request: Request):
    _check(body.ids, request)
    from ..services import libraryfs

    read = 0
    for media_id in body.ids:
        row = q1("SELECT rel_path FROM media WHERE id=?", (media_id,))
        if row and xmpsvc.import_sidecar(media_id, libraryfs.abs_path(row["rel_path"])):
            read += 1
    return {"read": read}


@router.post("/export", status_code=202)
def export(body: ExportIn, request: Request):
    _check(body.ids, request)
    dest = os.path.abspath(os.path.expanduser(body.dest))
    ids = list(body.ids)
    opts = dict(body.options)
    opts["allow_private"] = False
    return {"job_id": jobs.start("export", lambda state: outputsvc.export_job(ids, dest, opts, state)), "dest": dest}


@router.post("/contact-sheet")
def contact_sheet(body: SheetIn, request: Request):
    _check(body.ids, request)
    pdf = outputsvc.contact_sheet(body.ids, body.options)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="contact-sheet.pdf"', "Cache-Control": "no-store"})


@router.post("/print-sheet")
def print_sheet(body: SheetIn, request: Request):
    _check(body.ids, request)
    pdf = outputsvc.print_sheet(body.ids, body.options)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="print.pdf"', "Cache-Control": "no-store"})


@router.get("/workflows")
def workflows():
    return {"workflows": [{"id": r["id"], "name": r["name"], "steps": json.loads(r["steps_json"])} for r in q("SELECT * FROM workflows ORDER BY name COLLATE NOCASE")],
            "kinds": list(outputsvc.STEP_KINDS)}


def _valid_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clean = [s for s in steps if s.get("kind") in outputsvc.STEP_KINDS]
    if not clean:
        raise HTTPException(400, detail="Add at least one step")
    return clean


@router.post("/workflows", status_code=201)
def create_workflow(body: WorkflowIn):
    steps = _valid_steps(body.steps)
    existing = q1("SELECT id FROM workflows WHERE name=?", (body.name.strip(),))
    if existing:
        ex("UPDATE workflows SET steps_json=? WHERE id=?", (json.dumps(steps), existing["id"]))
        return {"id": existing["id"]}
    return {"id": ex("INSERT INTO workflows(name, steps_json, created_ts) VALUES(?,?,?)", (body.name.strip(), json.dumps(steps), time.time()))}


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: int):
    ex("DELETE FROM workflows WHERE id=?", (workflow_id,))
    return {"ok": True}


@router.post("/workflows/{workflow_id}/run", status_code=202)
def run_workflow(workflow_id: int, body: IdsIn, request: Request):
    row = q1("SELECT steps_json FROM workflows WHERE id=?", (workflow_id,))
    if row is None:
        raise HTTPException(404, detail="No such workflow")
    _check(body.ids, request)
    steps = json.loads(row["steps_json"])
    ids = list(body.ids)
    return {"job_id": jobs.start("workflow", lambda state: outputsvc.run_workflow(steps, ids, state))}
