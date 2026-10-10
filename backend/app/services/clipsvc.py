import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..config import models_dir
from ..db import ex, q, q1
from . import thumbs

MODEL = "clip_vit_b32_laion2b_int8.onnx"
VOCAB = "clip_vocab.json"
MERGES = "clip_merges.txt"
SIZE = 224
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
BATCH = 16
SEARCH_FLOOR = 0.22
SIMILAR_FLOOR = 0.6
SEARCH_BAND = 0.06
PET_SAME = 0.78

SUBJECTS = [
    "dog", "cat", "bird", "horse", "fish", "insect", "butterfly", "cow", "sheep", "llama", "wild animal",
    "baby", "child", "group of people", "selfie", "portrait",
    "food", "drink", "cake", "fruit", "flower", "plant", "tree",
    "car", "bicycle", "motorcycle", "boat", "airplane", "train", "bus",
    "building", "house", "church", "bridge", "city street", "shop front", "pub", "restaurant", "kitchen", "bedroom", "office",
    "beach", "mountain", "lake", "river", "forest", "snow", "desert", "garden", "park", "waterfall",
    "sunset", "night sky", "fireworks", "fire", "stop sign", "road",
    "concert", "party", "wedding", "christmas tree", "sports",
    "computer", "phone", "book", "painting", "sculpture", "toy", "snowman",
]
CONTENT = {
    "document": "a scanned page of a printed document",
    "receipt": "a photo of a shop receipt",
    "handwriting": "a photo of handwritten notes",
    "illustration": "an illustration or drawing",
    "diagram": "a labelled diagram",
    "whiteboard": "a photo of a whiteboard",
    "menu": "a photo of a restaurant menu",
    "map": "a photo of a map",
}
PETS = {"dog", "cat"}

_lock = threading.Lock()
_session = None
_tok = None
_label_mat: Optional[np.ndarray] = None
_label_names: List[Tuple[str, str]] = []
_matrix: Optional[Tuple[np.ndarray, np.ndarray]] = None
_matrix_stamp = 0.0
_dirty = time.time()
_search_cache: Dict[Tuple[str, int], Tuple[float, List[Tuple[int, float]]]] = {}


def paths() -> Dict[str, str]:
    base = models_dir()
    return {"model": os.path.join(base, MODEL), "vocab": os.path.join(base, VOCAB), "merges": os.path.join(base, MERGES)}


def status() -> Dict[str, Any]:
    missing = [name for name, path in paths().items() if not os.path.isfile(path)]
    try:
        import onnxruntime  # noqa: F401
        runtime = True
    except Exception:
        runtime = False
    pending = q1("SELECT COUNT(*) AS n FROM media WHERE clip_state=0 AND trashed_ts IS NULL AND live_of IS NULL")["n"]
    done = q1("SELECT COUNT(*) AS n FROM clip_vectors")["n"]
    return {"ready": runtime and not missing, "runtime": runtime, "missing": missing, "pending": pending, "indexed": done}


def ready() -> bool:
    return bool(status()["ready"])


def _engine():
    global _session, _tok
    with _lock:
        if _session is None:
            import onnxruntime as ort

            from .cliptok import Tokenizer

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) - 1))
            p = paths()
            _session = ort.InferenceSession(p["model"], sess_options=opts, providers=["CPUExecutionProvider"])
            _tok = Tokenizer(p["vocab"], p["merges"])
        return _session, _tok


def _norm(mat: np.ndarray) -> np.ndarray:
    return mat / np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-8)


def _pixels(img) -> np.ndarray:
    from PIL import Image

    img = img.convert("RGB")
    w, h = img.size
    scale = SIZE / min(w, h)
    img = img.resize((max(SIZE, round(w * scale)), max(SIZE, round(h * scale))), Image.BICUBIC)
    w, h = img.size
    left, top = (w - SIZE) // 2, (h - SIZE) // 2
    arr = np.asarray(img.crop((left, top, left + SIZE, top + SIZE)), dtype=np.float32) / 255.0
    return ((arr - MEAN) / STD).transpose(2, 0, 1)


def embed_images(images: List[Any]) -> np.ndarray:
    session, _ = _engine()
    pixels = np.stack([_pixels(img) for img in images]).astype(np.float32)
    ids = np.array([[49406, 49407]], dtype=np.int64)
    out = session.run(["image_embeds"], {"pixel_values": pixels, "input_ids": ids, "attention_mask": np.ones_like(ids)})[0]
    return _norm(out.astype(np.float32))


def embed_texts(texts: List[str]) -> np.ndarray:
    session, tok = _engine()
    encoded = [tok.encode(t) for t in texts]
    width = max(len(e) for e in encoded)
    ids = np.zeros((len(encoded), width), dtype=np.int64)
    mask = np.zeros((len(encoded), width), dtype=np.int64)
    for i, e in enumerate(encoded):
        ids[i, : len(e)] = e
        mask[i, : len(e)] = 1
    blank = np.zeros((1, 3, SIZE, SIZE), dtype=np.float32)
    out = session.run(["text_embeds"], {"pixel_values": blank, "input_ids": ids, "attention_mask": mask})[0]
    return _norm(out.astype(np.float32))


def _labels() -> Tuple[np.ndarray, List[Tuple[str, str]]]:
    global _label_mat, _label_names
    if _label_mat is None:
        names = [(s, "subject") for s in SUBJECTS] + [(k, "content") for k in CONTENT]
        prompts = [f"a photo of a {s}." for s in SUBJECTS] + list(CONTENT.values())
        _label_mat = embed_texts(prompts)
        _label_names = names
    return _label_mat, _label_names


def classify(vec: np.ndarray) -> List[Tuple[str, str, float]]:
    mat, names = _labels()
    sims = mat @ vec
    logits = sims * 100.0
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    out = []
    for i in np.argsort(-probs)[:4]:
        if probs[i] >= 0.12 and sims[i] >= 0.18:
            out.append((names[i][0], names[i][1], float(probs[i])))
    return out


def _qr(path: str) -> bool:
    try:
        import cv2

        img = cv2.imread(path)
        if img is None:
            return False
        found, _ = cv2.QRCodeDetector().detect(img)
        return bool(found)
    except Exception:
        return False


def _assign_pet(media_id: int, species: str, vec: np.ndarray) -> None:
    best, best_sim = None, 0.0
    for pet in q("SELECT id, centroid, members FROM pets WHERE species=?", (species,)):
        centroid = np.frombuffer(pet["centroid"], dtype=np.float32)
        sim = float(centroid @ vec / max(np.linalg.norm(centroid), 1e-8))
        if sim > best_sim:
            best, best_sim = pet, sim
    if best is not None and best_sim >= PET_SAME:
        n = best["members"]
        centroid = np.frombuffer(best["centroid"], dtype=np.float32) * n + vec
        centroid = centroid / max(np.linalg.norm(centroid), 1e-8)
        ex("UPDATE pets SET centroid=?, members=members+1 WHERE id=?", (centroid.astype(np.float32).tobytes(), best["id"]))
        ex("UPDATE media SET pet_id=? WHERE id=?", (best["id"], media_id))
        return
    pid = ex("INSERT INTO pets(species, cover_media_id, centroid, members, created_ts) VALUES(?,?,?,1,?)",
             (species, media_id, vec.astype(np.float32).tobytes(), time.time()))
    ex("UPDATE media SET pet_id=? WHERE id=?", (pid, media_id))


def _store(media_id: int, vec: np.ndarray, path: str) -> None:
    ex("INSERT OR REPLACE INTO clip_vectors(media_id, vec) VALUES(?,?)", (media_id, vec.astype(np.float16).tobytes()))
    ex("DELETE FROM media_labels WHERE media_id=? AND kind IN ('subject','content')", (media_id,))
    labels = classify(vec)
    for name, kind, score in labels:
        ex("INSERT OR REPLACE INTO media_labels(media_id, label, kind, score) VALUES(?,?,?,?)", (media_id, name, kind, score))
    if _qr(path):
        ex("INSERT OR REPLACE INTO media_labels(media_id, label, kind, score) VALUES(?,?,?,?)", (media_id, "qr code", "content", 1.0))
    pet = next((name for name, kind, _ in labels if name in PETS), None)
    if pet:
        _assign_pet(media_id, pet, vec)
    try:
        from . import lookup

        lookup.apply(media_id, vec)
    except Exception:
        pass
    ex("UPDATE media SET clip_state=1 WHERE id=?", (media_id,))


def index_job(state: Dict[str, Any]) -> None:
    global _dirty
    info = status()
    if not info["ready"]:
        raise RuntimeError("CLIP model missing: " + ", ".join(info["missing"] or ["onnxruntime"]))
    from PIL import Image

    counts = {"indexed": 0, "failed": 0, "total": info["pending"]}
    state["counts"] = counts
    rows = q("SELECT id, rel_path, kind FROM media WHERE clip_state=0 AND trashed_ts IS NULL AND live_of IS NULL ORDER BY created_ts DESC")
    for start in range(0, len(rows), BATCH):
        chunk, images, paths_ = [], [], []
        for row in rows[start:start + BATCH]:
            path = thumbs.ensure_thumb(row["id"], row["rel_path"], row["kind"], 384)
            img = None
            if path and os.path.isfile(path):
                try:
                    img = Image.open(path)
                    img.load()
                except Exception:
                    img = None
            if img is None:
                ex("UPDATE media SET clip_state=2 WHERE id=?", (row["id"],))
                counts["failed"] += 1
                continue
            chunk.append(row)
            images.append(img)
            paths_.append(path)
        if not chunk:
            continue
        vecs = embed_images(images)
        for row, vec, path in zip(chunk, vecs, paths_):
            _store(row["id"], vec, path)
            counts["indexed"] += 1
        _dirty = time.time()
    _refresh_pet_covers()


def _refresh_pet_covers() -> None:
    for pet in q("SELECT id FROM pets"):
        row = q1("""SELECT COUNT(*) AS n FROM media WHERE pet_id=? AND trashed_ts IS NULL""", (pet["id"],))
        if row["n"] == 0:
            ex("DELETE FROM pets WHERE id=?", (pet["id"],))
            continue
        cover = q1("""SELECT id FROM media WHERE pet_id=? AND trashed_ts IS NULL AND private=0 AND hidden=0
                      ORDER BY favorite DESC, rating DESC, created_ts DESC LIMIT 1""", (pet["id"],))
        ex("UPDATE pets SET members=?, cover_media_id=? WHERE id=?", (row["n"], cover["id"] if cover else None, pet["id"]))


def _vectors() -> Tuple[np.ndarray, np.ndarray]:
    global _matrix, _matrix_stamp
    with _lock:
        if _matrix is None or _matrix_stamp < _dirty:
            rows = q("SELECT media_id, vec FROM clip_vectors")
            ids = np.array([r["media_id"] for r in rows], dtype=np.int64)
            mat = np.stack([np.frombuffer(r["vec"], dtype=np.float16) for r in rows]).astype(np.float32) if rows else np.zeros((0, 512), np.float32)
            _matrix, _matrix_stamp = (ids, mat), time.time()
        return _matrix


def search(text: str, limit: int = 2000) -> List[Tuple[int, float]]:
    if not text.strip() or not ready():
        return []
    key = (text.strip().lower(), limit)
    hit = _search_cache.get(key)
    if hit is not None and hit[0] >= _dirty:
        return hit[1]
    ids, mat = _vectors()
    if not len(ids):
        return []
    vec = embed_texts([f"a photo of {text.strip()}"])[0]
    sims = mat @ vec
    top = float(sims.max())
    floor = max(SEARCH_FLOOR, top - SEARCH_BAND)
    order = np.argsort(-sims)[:limit]
    found = [(int(ids[i]), float(sims[i])) for i in order if sims[i] >= floor]
    if len(_search_cache) > 64:
        _search_cache.clear()
    _search_cache[key] = (time.time(), found)
    return found


def similar(media_id: int, limit: int = 200) -> List[Tuple[int, float]]:
    ids, mat = _vectors()
    hit = np.nonzero(ids == media_id)[0]
    if not hit.size:
        return []
    sims = mat @ mat[hit[0]]
    order = np.argsort(-sims)[: limit + 1]
    return [(int(ids[i]), float(sims[i])) for i in order if ids[i] != media_id and sims[i] >= SIMILAR_FLOOR]


def mark_dirty() -> None:
    global _dirty
    _dirty = time.time()


def forget(media_id: int) -> None:
    ex("DELETE FROM clip_vectors WHERE media_id=?", (media_id,))
    ex("UPDATE media SET clip_state=0 WHERE id=?", (media_id,))
    mark_dirty()
