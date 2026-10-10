import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from .config import env, library_root

_lock = threading.Lock()


def config_dir() -> str:
    if sys.platform == "darwin":
        default = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "DAM")
    elif os.name == "nt":
        default = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DAM")
    else:
        default = os.path.join(os.path.expanduser("~"), ".config", "dam")
    return env("CONFIG", default)


def _file() -> str:
    return os.path.join(config_dir(), "libraries.json")


def _read() -> Dict[str, Any]:
    try:
        with open(_file(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: Dict[str, Any]) -> None:
    os.makedirs(config_dir(), exist_ok=True)
    tmp = _file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, _file())


def current() -> Optional[str]:
    path = _read().get("current")
    return path if path and os.path.isdir(path) else None


def listing() -> List[Dict[str, Any]]:
    with _lock:
        data = _read()
        libs = data.get("libraries") or []
        active = os.path.abspath(library_root())
        if not any(os.path.abspath(lib.get("path", "")) == active for lib in libs):
            libs.insert(0, {"path": active, "name": os.path.basename(active.rstrip(os.sep)) or active, "opened_ts": time.time()})
    out = []
    for lib in libs:
        path = lib.get("path", "")
        out.append({**lib, "active": os.path.abspath(path) == active, "exists": os.path.isfile(os.path.join(path, "dam.db")) or os.path.isdir(path)})
    return out


def remember(path: str, name: Optional[str] = None) -> None:
    with _lock:
        data = _read()
        libs = [lib for lib in data.get("libraries") or [] if os.path.abspath(lib.get("path", "")) != os.path.abspath(path)]
        libs.insert(0, {"path": os.path.abspath(path), "name": name or os.path.basename(path.rstrip(os.sep)) or path, "opened_ts": time.time()})
        data["libraries"] = libs[:20]
        data["current"] = os.path.abspath(path)
        _write(data)


def forget(path: str) -> None:
    with _lock:
        data = _read()
        data["libraries"] = [lib for lib in data.get("libraries") or [] if os.path.abspath(lib.get("path", "")) != os.path.abspath(path)]
        if data.get("current") and os.path.abspath(data["current"]) == os.path.abspath(path):
            data.pop("current", None)
        _write(data)
