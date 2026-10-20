import threading
from typing import Callable, List

INTERVAL_S = 6 * 3600

_tasks: List[Callable[[], object]] = []
_started = False
_lock = threading.Lock()
_wake = threading.Event()


def register(task: Callable[[], object]) -> None:
    if task not in _tasks:
        _tasks.append(task)


def run_once() -> None:
    from ..db import reset_thread_conn

    try:
        for task in list(_tasks):
            try:
                task()
            except Exception:
                pass
    finally:
        reset_thread_conn()


def _loop() -> None:
    while True:
        _wake.wait(INTERVAL_S)
        _wake.clear()
        run_once()


def start() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="formDAM-housekeeping", daemon=True).start()
