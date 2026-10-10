from typing import Any, Dict, List

from .. import jobs

_steps: List[Dict[str, Any]] = []


def register(kind: str, ready, target) -> None:
    _steps.append({"kind": kind, "ready": ready, "target": target})


def start_after_import(counts: Dict[str, Any]) -> List[str]:
    if not counts or not counts.get("imported"):
        return []
    started = []
    for step in _steps:
        try:
            if not step["ready"]():
                continue
        except Exception:
            continue
        if jobs.running(step["kind"]):
            continue
        jobs.start(step["kind"], step["target"])
        started.append(step["kind"])
    return started


def _register_defaults() -> None:
    from . import facesvc, ocrsvc

    register("ocr", lambda: bool(ocrsvc.engine_name()), ocrsvc.scan_job)
    register("faces", lambda: bool(facesvc.status()["ready"]), facesvc.scan_job)


_register_defaults()
