import errno
import os
import string
import sys
from typing import List

ENV_DIR_NAMES = {".venv", "venv", ".virtualenv", "virtualenv", "node_modules", "__pycache__", ".tox", ".git"}
OS_META_DIRS = {".trashes", ".spotlight-v100", ".fseventsd", ".temporaryitems", "$recycle.bin", "system volume information"}


def looks_like_env(path: str) -> bool:
    try:
        return os.path.isfile(os.path.join(path, "pyvenv.cfg")) or os.path.isdir(os.path.join(path, "conda-meta"))
    except OSError:
        return False


PACKAGE_EXTS = {
    "photoslibrary",
    "migratedphotolibrary",
    "aplibrary",
    "tvlibrary",
    "musiclibrary",
    "imovielibrary",
    "fcpbundle",
    "theater",
    "bundle",
    "framework",
    "app",
}


def is_package_dir(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    return ext in PACKAGE_EXTS


def list_roots() -> List[dict]:
    roots: List[dict] = []
    home = os.path.expanduser("~")
    if os.path.isdir(home):
        roots.append({"path": home, "label": "Home", "kind": "home"})
    if sys.platform == "darwin":
        originals = os.path.join(home, "Pictures", "Photos Library.photoslibrary", "originals")
        if os.path.isdir(originals):
            roots.append({"path": originals, "label": "Photos Library originals", "kind": "photos"})
    if os.name == "nt":
        lister = getattr(os, "listdrives", None)
        if lister is not None:
            letters = list(lister())
        else:
            letters = [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
        for letter in letters:
            roots.append({"path": letter, "label": letter, "kind": "drive"})
        return roots
    roots.append({"path": "/", "label": "System root", "kind": "root"})
    for base in ("/Volumes", "/media", "/run/media", "/mnt"):
        if not os.path.isdir(base):
            continue
        try:
            entries = sorted(os.listdir(base))
        except OSError:
            continue
        for name in entries:
            full = os.path.join(base, name)
            if not os.path.isdir(full) or os.path.islink(full):
                continue
            roots.append({"path": full, "label": name, "kind": "drive"})
            if base in ("/media", "/run/media"):
                try:
                    for sub in sorted(os.listdir(full)):
                        sub_full = os.path.join(full, sub)
                        if os.path.isdir(sub_full) and not os.path.islink(sub_full):
                            roots.append({"path": sub_full, "label": f"{name}/{sub}", "kind": "drive"})
                except OSError:
                    continue
    return roots


def list_dirs(path: str) -> dict:
    target = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(target):
        raise NotADirectoryError(path)
    dirs: List[dict] = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    name_lower = entry.name.lower()
                    flagged = (
                        name_lower in ENV_DIR_NAMES
                        or name_lower in OS_META_DIRS
                        or looks_like_env(entry.path)
                    )
                    dirs.append(
                        {
                            "name": entry.name,
                            "path": entry.path,
                            "is_env": flagged,
                            "is_pkg": is_package_dir(entry.name),
                        }
                    )
                except OSError:
                    continue
    except OSError as exc:
        if sys.platform == "darwin" and getattr(exc, "errno", None) in (errno.EPERM, errno.EACCES):
            raise PermissionError(
                f"{exc}. macOS blocked this read: grant the app Full Disk Access in "
                "System Settings > Privacy & Security > Full Disk Access, then try again."
            )
        raise PermissionError(str(exc))
    dirs.sort(key=lambda item: item["name"].lower())
    parent = os.path.dirname(target)
    return {"path": target, "parent": parent if parent != target else None, "dirs": dirs}
