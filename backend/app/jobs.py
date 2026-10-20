import threading
import traceback
import uuid
from typing import Any, Callable, Dict, Optional

_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def start(kind: str, target: Callable[[Dict[str, Any]], None]) -> str:
    job_id = uuid.uuid4().hex[:12]
    state: Dict[str, Any] = {"id": job_id, "kind": kind, "phase": "running", "counts": {}, "error": ""}
    with _lock:
        _jobs[job_id] = state

    def run() -> None:
        from .db import reset_thread_conn
        try:
            target(state)
            if state["phase"] == "running":
                state["phase"] = "done"
        except Exception as exc:
            state["phase"] = "error"
            state["error"] = f"{exc}"
            state["trace"] = traceback.format_exc()
        finally:
            reset_thread_conn()

    thread = threading.Thread(target=run, name=f"formDAM-{kind}", daemon=True)
    thread.start()
    return job_id


def get(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _jobs.get(job_id)


def running(kind: str) -> Optional[Dict[str, Any]]:
    with _lock:
        for state in _jobs.values():
            if state["kind"] == kind and state["phase"] == "running":
                return state
    return None
