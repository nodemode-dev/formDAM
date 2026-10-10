import os

VERSION = "1.13.9"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_ENV_PREFIX = "DAMP_"


def env(name: str, default: str) -> str:
    return os.environ.get(f"DAM_{name}", os.environ.get(f"{LEGACY_ENV_PREFIX}{name}", default))


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
