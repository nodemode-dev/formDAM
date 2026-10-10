import gzip
import hashlib
import json
import math
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .. import jobs
from ..config import cache_dir
from ..db import ex, q, q1
from . import clipsvc, species
from .lookupdata import ANIMALS, BIRDS, CATS, DOGS, FLOWERS, INSECTS, KIND_LABELS, LANDMARKS, PLANTS

VERSION = 2
WORLD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "lookup_world.json.gz")
FAR_LANDMARKS = 1500
ORGANISMS = {"bird", "insect", "flower", "plant", "animal", "fungus"}
BIO_MASS = 0.2
DOMESTIC = {"Canis lupus": "dog", "Canis familiaris": "dog", "Felis catus": "cat", "Felis silvestris": "cat"}
CLEAR_GATE = 0.6
CLEAR_MIN = 0.15
CLEAR_MARGIN = 1.5
FOOD_PICK = 0.25


def _world() -> Dict[str, Any]:
    try:
        with gzip.open(WORLD, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"landmarks": [], "art": [], "food": []}


_WORLD = _world()
WORLD_LANDMARKS = [(row[0], row[1], row[2], row[3]) for row in _WORLD["landmarks"]]
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
    "animal": "a photo of a wild animal, farm animal, fish, reptile or frog.",
    "fungus": "a photo of a mushroom or fungus.",
    "landmark": "a photo of a famous landmark, monument or building.",
    "art": "a photo of a famous painting, sculpture or work of art.",
    "food": "a photo of food, a dish or a drink.",
}
NEUTRAL = [
    "a photo of a person.", "a photo of a group of people.", "a photo of a room.",
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
    "art": "a photo of {}, a famous work of art.",
    "food": "a photo of {}, a type of food or drink.",
}
VOCAB = {"dog": DOGS, "cat": CATS, "bird": BIRDS, "insect": INSECTS, "flower": FLOWERS, "plant": PLANTS, "animal": ANIMALS,
         "landmark": sorted({name for name, *_ in LANDMARKS} | {row[0] for row in _WORLD["landmarks"][:FAR_LANDMARKS]}),
         "art": [row[0] for row in _WORLD["art"]], "food": [row[0] for row in _WORLD["food"]]}
CREATORS = {row[0]: row[1] for row in _WORLD["art"] if row[1]}
PROMPTS = {"art": [f"a photo of {row[0]} by {row[1]}, a famous work of art." if row[1] else TEMPLATES["art"].format(row[0])
                   for row in _WORLD["art"]]}

_lock = threading.Lock()
_mats: Dict[str, np.ndarray] = {}


def _mat(key: str, prompts: List[str]) -> np.ndarray:
    with _lock:
        hit = _mats.get(key)
    if hit is None:
        digest = hashlib.sha1("\n".join(prompts).encode("utf-8")).hexdigest()[:20]
        path = os.path.join(cache_dir(), "lookup", f"{digest}.npy")
        try:
            hit = np.load(path).astype(np.float32)
        except (OSError, ValueError):
            hit = np.concatenate([clipsvc.embed_texts(prompts[i:i + 64]) for i in range(0, len(prompts), 64)])
            if len(prompts) > 64:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    np.save(path + ".part.npy", hit.astype(np.float16))
                    os.replace(path + ".part.npy", path)
                except OSError:
                    pass
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
    for name, la, lo, radius in list(LANDMARKS) + WORLD_LANDMARKS:
        if abs(lat - la) * 111.0 > radius or name in names:
            continue
        if _km(lat, lon, la, lo) <= radius:
            names.append(name)
    return names[:24]


def _within(group: str, vec: np.ndarray) -> List[Tuple[str, float, float]]:
    names = VOCAB[group]
    mat = _mat(group, PROMPTS.get(group) or [TEMPLATES[group].format(n) for n in names])
    sims = mat @ vec
    p = _softmax(sims)
    return [(names[i], float(p[i]), float(sims[i])) for i in np.argsort(-p)[:3]]


def _landmark_near(vec: np.ndarray, names: List[str]) -> Optional[Tuple[str, float]]:
    prompts = [TEMPLATES["landmark"].format(n) for n in names] + NEUTRAL
    mat = _mat("near:" + "|".join(names), prompts)
    p = _softmax(mat @ vec)
    best = int(np.argmax(p[: len(names)]))
    return (names[best], float(p[best])) if p[best] >= NEAR_MIN else None


def _species(image: Callable[[], Any]) -> Optional[Dict[str, Any]]:
    try:
        img = image()
        return species.identify(species.embed(img)) if img is not None else None
    except Exception:
        return None


def identify(vec: np.ndarray, lat: Optional[float] = None, lon: Optional[float] = None,
             image: Optional[Callable[[], Any]] = None) -> List[Dict[str, Any]]:
    keys = list(GROUPS)
    bio = image is not None and species.ready()
    gate = _softmax(_mat("groups", [GROUPS[k] for k in keys] + NEUTRAL) @ vec)
    found: List[Dict[str, Any]] = []
    close = nearby(lat, lon)
    if close:
        hit = _landmark_near(vec, close)
        if hit:
            found.append({"name": hit[0], "kind": "landmark", "score": hit[1], "near": True})
    order = sorted(range(len(keys)), key=lambda i: -gate[i])
    weight = {k: float(gate[n]) for n, k in enumerate(keys)}
    skip = set()
    mass = sum(weight[k] for k in ORGANISMS | {"dog", "cat"})
    if bio and mass >= BIO_MASS and mass > weight["food"]:
        hit = _species(image)
        if hit:
            skip = ORGANISMS | {"dog", "cat"}
            pet = DOMESTIC.get(hit["scientific"])
            if pet:
                top = _within(pet, vec)
                if top[0][1] >= PICK_MIN:
                    found.append({"name": top[0][0], "kind": pet, "score": top[0][1], "alternatives": [n for n, p, _ in top[1:] if p >= 0.1]})
                else:
                    found.append({"name": GENERIC[pet], "kind": pet, "score": hit["score"], "alternatives": [n for n, p, _ in top if p >= 0.05]})
            else:
                if hit["kind"] == "plant" and weight["flower"] > weight["plant"]:
                    hit["kind"] = "flower"
                if hit["scientific"].lower() != hit["name"].lower():
                    hit["detail"] = hit["scientific"]
                found.append(hit)
    for rank, i in enumerate(order[:2]):
        group = keys[i]
        if group in skip or gate[i] < (GROUP_MIN if rank == 0 else SECOND_MIN) or (group == "landmark" and any(f["kind"] == "landmark" for f in found)):
            continue
        if group not in VOCAB or not VOCAB[group]:
            continue
        top = _within(group, vec)
        name, prob, sim = top[0]
        if group == "landmark" and (prob < FAR_MIN or sim < FAR_SIM):
            continue
        clear = gate[i] >= CLEAR_GATE and prob >= CLEAR_MIN and prob >= CLEAR_MARGIN * top[1][1]
        if prob >= PICK_MIN or (clear and group in ("art", "food")) or (group == "food" and gate[i] >= CLEAR_GATE and prob >= FOOD_PICK):
            alts = [n for n, p, _ in top[1:] if p >= 0.1]
            found.append({"name": name, "kind": group, "score": prob, "alternatives": alts})
        elif gate[i] >= SPECIES_GATE and group in GENERIC:
            alts = [n for n, p, _ in top if p >= 0.05]
            found.append({"name": GENERIC[group], "kind": group, "score": float(gate[i]), "alternatives": alts})
    for item in found:
        item["kind_label"] = KIND_LABELS[item["kind"]]
        item["wiki"] = item.get("wiki") or item["name"].replace(" ", "_")
        if item["kind"] == "art" and item["name"] in CREATORS:
            item["detail"] = CREATORS[item["name"]]
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
    row = q1("SELECT lat, lon, rel_path, kind FROM media WHERE id=?", (media_id,))

    def image():
        from PIL import Image

        from . import thumbs

        path = thumbs.ensure_thumb(media_id, row["rel_path"], row["kind"], 384) if row else None
        return Image.open(path).convert("RGB") if path else None

    found = identify(vec, row["lat"] if row else None, row["lon"] if row else None, image)
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
