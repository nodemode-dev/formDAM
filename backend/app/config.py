import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_version() -> str:
    for path in (os.path.join(getattr(sys, "_MEIPASS", ""), "package.json"),
                 os.path.join(REPO_ROOT, "frontend", "package.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return str(json.load(fh)["version"])
        except (OSError, ValueError, KeyError):
            continue
    return "0.0.0"


VERSION = _build_version()
ENV_PREFIX = "FORMDAM_"
LEGACY_ENV_PREFIXES = ("DAM_", "DAMP_")


def env(name: str, default: str) -> str:
    for prefix in (ENV_PREFIX, *LEGACY_ENV_PREFIXES):
        value = os.environ.get(f"{prefix}{name}")
        if value is not None:
            return value
    return default


def library_root() -> str:
    return os.path.abspath(env("LIBRARY", os.path.join(REPO_ROOT, "library")))


def originals_dir() -> str:
    return os.path.join(library_root(), "originals")


def cache_dir() -> str:
    return os.path.join(library_root(), "cache")


def db_path() -> str:
    return os.path.join(library_root(), "dam.db")


def models_dir() -> str:
    return env("MODELS", os.path.join(REPO_ROOT, "backend", "models"))


def face_threshold() -> float:
    try:
        return float(env("FACE_THRESHOLD", "0.55"))
    except ValueError:
        return 0.42


def trash_retention_days() -> int:
    try:
        return int(env("TRASH_DAYS", "30"))
    except ValueError:
        return 30
