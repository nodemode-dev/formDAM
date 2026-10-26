import hashlib
import os
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
OWN_ORIGIN = "http://127.0.0.1"
WINDOW_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173", "tauri://localhost", "http://tauri.localhost"]
VERSION_SITES = [
    ("frontend/package.json", r'^  "version": "([^"]+)"'),
    ("frontend/package-lock.json", r'^  "version": "([^"]+)"'),
    ("frontend/package-lock.json", r'^      "version": "([^"]+)"'),
    ("src-tauri/Cargo.toml", r'^version = "([^"]+)"'),
    ("src-tauri/Cargo.lock", r'name = "formdam-desktop"\nversion = "([^"]+)"'),
]


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hashes(root) -> dict:
    out = {}
    for base, _, names in os.walk(root):
        for name in names:
            full = os.path.join(base, name)
            out[os.path.relpath(full, root)] = sha(full)
    return out
