import json
import math
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .. import jobs
from ..db import ex, q, q1
from . import clipsvc
from .lookupdata import ANIMALS, BIRDS, CATS, DOGS, FLOWERS, INSECTS, KIND_LABELS, LANDMARKS, PLANTS

VERSION = 1
GROUP_MIN = 0.2
SECOND_MIN = 0.015
SPECIES_GATE = 0.8
GENERIC = {"dog": "Dog", "cat": "Cat", "bird": "Bird", "insect": "Insect", "flower": "Flower", "plant": "Plant"}
PICK_MIN = 0.3
NEAR_MIN = 0.35
FAR_MIN = 0.5
FAR_SIM = 0.25

GROUPS = {
    "dog": "a photo of a dog.",
    "cat": "a photo of a cat.",
    "bird": "a photo of a bird.",
    "insect": "a close-up photo of an insect, butterfly or spider.",
    "flower": "a photo of a flower.",
    "plant": "a photo of a plant or tree.",
    "animal": "a photo of a wild or farm animal.",
    "landmark": "a photo of a famous landmark, monument or building.",
}
NEUTRAL = [
    "a photo of a person.", "a photo of a group of people.", "a photo of food.", "a photo of a room.",
    "a photo of a car.", "a screenshot.", "a photo of a document.", "a photo of a city street.", "a photo of a landscape.",
]
TEMPLATES = {
    "dog": "a photo of a {}, a type of dog.",
    "cat": "a photo of a {}, a type of cat.",
    "bird": "a photo of a {}, a type of bird.",
    "insect": "a close-up photo of a {}.",
    "flower": "a photo of a {}, a type of flower.",
    "plant": "a photo of a {}, a type of plant.",
    "animal": "a photo of a {}, a type of animal.",
    "landmark": "a photo of the {}, a famous landmark.",
}
VOCAB = {"dog": DOGS, "cat": CATS, "bird": BIRDS, "insect": INSECTS, "flower": FLOWERS, "plant": PLANTS, "animal": ANIMALS,
         "landmark": sorted({name for name, *_ in LANDMARKS})}

_lock = threading.Lock()
_mats: Dict[str, np.ndarray] = {}


def _mat(key: str, prompts: List[str]) -> np.ndarray:
    with _lock:
        hit = _mats.get(key)
    if hit is None:
        hit = clipsvc.embed_texts(prompts)
        with _lock:
            _mats[key] = hit
    return hit


def _softmax(sims: np.ndarray) -> np.ndarray:
    logits = sims * 100.0
    p = np.exp(logits - logits.max())
    return p / p.sum()


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def nearby(lat: Optional[float], lon: Optional[float]) -> List[str]:
    if lat is None or lon is None:
        return []
    names = []
    for name, la, lo, radius in LANDMARKS:
        if _km(lat, lon, la, lo) <= radius and name not in names:
            names.append(name)
    return names


def _within(group: str, vec: np.ndarray) -> List[Tuple[str, float, float]]:
    names = VOCAB[group]
    mat = _mat(group, [TEMPLATES[group].format(n) for n in names])
    sims = mat @ vec
    p = _softmax(sims)
    return [(names[i], float(p[i]), float(sims[i])) for i in np.argsort(-p)[:3]]


def _landmark_near(vec: np.ndarray, names: List[str]) -> Optional[Tuple[str, float]]:
    prompts = [TEMPLATES["landmark"].format(n) for n in names] + NEUTRAL
    mat = _mat("near:" + "|".join(names), prompts)
    p = _softmax(mat @ vec)
    best = int(np.argmax(p[: len(names)]))
    return (names[best], float(p[best])) if p[best] >= NEAR_MIN else None


def identify(vec: np.ndarray, lat: Optional[float] = None, lon: Optional[float] = None) -> List[Dict[str, Any]]:
    keys = list(GROUPS)
    gate = _softmax(_mat("groups", [GROUPS[k] for k in keys] + NEUTRAL) @ vec)
    found: List[Dict[str, Any]] = []
    close = nearby(lat, lon)
    if close:
        hit = _landmark_near(vec, close)
        if hit:
            found.append({"name": hit[0], "kind": "landmark", "score": hit[1], "near": True})
    order = sorted(range(len(keys)), key=lambda i: -gate[i])
    for rank, i in enumerate(order[:2]):
        group = keys[i]
        if gate[i] < (GROUP_MIN if rank == 0 else SECOND_MIN) or (group == "landmark" and found):
            continue
        top = _within(group, vec)
        name, prob, sim = top[0]
        if group == "landmark" and (prob < FAR_MIN or sim < FAR_SIM):
            continue
        if prob >= PICK_MIN:
            alts = [n for n, p, _ in top[1:] if p >= 0.1]
            found.append({"name": name, "kind": group, "score": prob, "alternatives": alts})
        elif gate[i] >= SPECIES_GATE and group in GENERIC:
            alts = [n for n, p, _ in top if p >= 0.05]
            found.append({"name": GENERIC[group], "kind": group, "score": float(gate[i]), "alternatives": alts})
    for item in found:
        item["kind_label"] = KIND_LABELS[item["kind"]]
        item["wiki"] = item["name"].replace(" ", "_")
    return found


def _vector(media_id: int) -> Optional[np.ndarray]:
    row = q1("SELECT vec FROM clip_vectors WHERE media_id=?", (media_id,))
    if row is None:
        return None
    return np.frombuffer(row["vec"], dtype=np.float16).astype(np.float32)


def apply(media_id: int, vec: Optional[np.ndarray] = None) -> List[Dict[str, Any]]:
    vec = _vector(media_id) if vec is None else vec
    if vec is None:
        return []
    row = q1("SELECT lat, lon FROM media WHERE id=?", (media_id,))
    found = identify(vec, row["lat"] if row else None, row["lon"] if row else None)
    ex("DELETE FROM media_labels WHERE media_id=? AND kind='lookup'", (media_id,))
    for item in found:
        if item["name"] in GENERIC.values():
            continue
        ex("INSERT OR IGNORE INTO media_labels(media_id, label, kind, score) VALUES(?,?,?,?)",
           (media_id, item["name"].lower(), "lookup", item["score"]))
    ex("UPDATE media SET lookup_state=?, lookup_json=? WHERE id=?", (VERSION, json.dumps(found) if found else None, media_id))
    return found


def scan_job(state: Dict[str, Any]) -> None:
    rows = q("""SELECT m.id FROM media m JOIN clip_vectors c ON c.media_id=m.id
                WHERE m.lookup_state<? AND m.trashed_ts IS NULL ORDER BY m.created_ts DESC""", (VERSION,))
    counts = {"done": 0, "found": 0, "total": len(rows)}
    state["counts"] = counts
    for row in rows:
        if apply(row["id"]):
            counts["found"] += 1
        counts["done"] += 1


def ensure() -> None:
    try:
        if not clipsvc.ready():
            return
        pending = q1("""SELECT COUNT(*) AS n FROM media m JOIN clip_vectors c ON c.media_id=m.id
                        WHERE m.lookup_state<? AND m.trashed_ts IS NULL""", (VERSION,))["n"]
    except Exception:
        return
    if pending and not jobs.running("lookup") and not jobs.running("clip"):
        jobs.start("lookup", scan_job)
