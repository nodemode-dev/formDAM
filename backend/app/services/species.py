import gzip
import json
import os
import sys
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..config import models_dir

MODEL = "bioclip_image_int8.onnx"
MATRIX = "bioclip_species_int8.npy"
SCALES = "bioclip_species_scale.npy"
NAMES = "bioclip_species.json.gz"
LOGIT = 100.0
CHUNK = 65536
TOP = 64
PICK = 0.3
RANK_PICK = 0.45

CLASS_KIND = {
    "Aves": "bird", "Insecta": "insect", "Arachnida": "insect", "Mammalia": "mammal", "Actinopterygii": "fish",
    "Chondrichthyes": "fish", "Reptilia": "reptile", "Amphibia": "amphibian", "Gastropoda": "mollusc", "Bivalvia": "mollusc",
    "Cephalopoda": "mollusc", "Malacostraca": "crustacean",
}

_lock = threading.Lock()
_state: Dict[str, Any] = {}


def _path(name: str) -> str:
    return os.path.join(models_dir(), name)


def ready() -> bool:
    if not all(os.path.isfile(_path(n)) for n in (MODEL, MATRIX, SCALES, NAMES)):
        return False
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def _load() -> Dict[str, Any]:
    with _lock:
        if not _state:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) - 1))
            _state["session"] = ort.InferenceSession(_path(MODEL), sess_options=opts, providers=["CPUExecutionProvider"])
            _state["matrix"] = np.load(_path(MATRIX), mmap_mode="r")
            _state["scale"] = np.load(_path(SCALES)).astype(np.float32)
            with gzip.open(_path(NAMES), "rt", encoding="utf-8") as fh:
                _state["taxa"] = json.load(fh)["taxa"]
        return _state


def embed(img) -> np.ndarray:
    from .clipsvc import _pixels

    st = _load()
    sess = st["session"]
    out = sess.run(None, {sess.get_inputs()[0].name: _pixels(img)[None].astype(np.float32)})[0][0]
    return (out / max(float(np.linalg.norm(out)), 1e-8)).astype(np.float32)


def _scores(vec: np.ndarray) -> np.ndarray:
    st = _load()
    mat, scale = st["matrix"], st["scale"]
    out = np.empty(mat.shape[0], np.float32)
    for start in range(0, mat.shape[0], CHUNK):
        block = np.asarray(mat[start:start + CHUNK], dtype=np.float32)
        out[start:start + CHUNK] = block @ vec
    return out * scale


def _display(taxon: List[str]) -> Tuple[str, str]:
    scientific = f"{taxon[5]} {taxon[6].split(' ')[0]}".strip()
    common = taxon[7].strip() if len(taxon) > 7 else ""
    return (common[:1].upper() + common[1:]) if common else scientific, scientific


def kind_of(taxon: List[str]) -> str:
    if taxon[0] == "Fungi":
        return "fungus"
    if taxon[0] in ("Plantae", "Viridiplantae"):
        return "plant"
    return CLASS_KIND.get(taxon[2], "animal")


def identify(vec: np.ndarray) -> Optional[Dict[str, Any]]:
    taxa = _load()["taxa"]
    logits = _scores(vec) * LOGIT
    top = np.argpartition(-logits, TOP)[:TOP]
    top = top[np.argsort(-logits[top])]
    p = np.exp(logits - logits[top[0]])
    p /= p.sum()
    ranked: List[Tuple[str, str, float, List[str]]] = []
    seen: Dict[str, int] = {}
    for i in top:
        name, scientific = _display(taxa[i])
        key = scientific.lower()
        if key in seen:
            entry = ranked[seen[key]]
            ranked[seen[key]] = (entry[0], entry[1], entry[2] + float(p[i]), entry[3])
            continue
        seen[key] = len(ranked)
        ranked.append((name, scientific, float(p[i]), taxa[i]))
    name, scientific, prob, taxon = ranked[0]
    alts = []
    for n, _, q, _ in ranked[1:6]:
        if q >= 0.08 and n.lower() != name.lower() and n.lower() not in (a.lower() for a in alts):
            alts.append(n)
    alts = alts[:3]
    if prob >= PICK:
        return {"name": name, "scientific": scientific, "score": prob, "kind": kind_of(taxon), "alternatives": alts,
                "wiki": scientific.replace(" ", "_"), "rank": "species"}
    for level, label in ((5, "genus"), (4, "family")):
        groups: Dict[str, float] = {}
        for _, _, q, t in ranked:
            groups[t[level]] = groups.get(t[level], 0.0) + q
        best = max(groups, key=lambda k: groups[k])
        if best and groups[best] >= RANK_PICK:
            members = [n for n, _, _, t in ranked if t[level] == best][:3]
            return {"name": best, "scientific": best, "score": groups[best], "kind": kind_of(taxon), "alternatives": members,
                    "wiki": best, "rank": label}
    return None


def prepare(src_npy: str, src_json: str, dest: str) -> None:
    emb = np.load(src_npy, mmap_mode="r")
    mat = emb.T if emb.shape[0] == 512 else emb
    rows = mat.shape[0]
    q = np.lib.format.open_memmap(os.path.join(dest, MATRIX + ".part"), mode="w+", dtype=np.int8, shape=(rows, mat.shape[1]))
    scale = np.empty(rows, np.float16)
    for start in range(0, rows, CHUNK):
        block = np.asarray(mat[start:start + CHUNK], dtype=np.float32)
        peak = np.maximum(np.abs(block).max(axis=1), 1e-8)
        q[start:start + CHUNK] = np.clip(np.rint(block / peak[:, None] * 127.0), -127, 127).astype(np.int8)
        scale[start:start + CHUNK] = (peak / 127.0).astype(np.float16)
    q.flush()
    del q
    with open(src_json, encoding="utf-8") as fh:
        names = json.load(fh)
    if len(names) != rows:
        raise SystemExit(f"species names ({len(names)}) and embeddings ({rows}) differ")
    taxa = [list(taxon) + [common or ""] for taxon, common in names]
    np.save(os.path.join(dest, SCALES), scale)
    with gzip.open(os.path.join(dest, NAMES), "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump({"taxa": taxa}, fh, separators=(",", ":"))
    os.replace(os.path.join(dest, MATRIX + ".part"), os.path.join(dest, MATRIX))


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "prepare":
        raise SystemExit("usage: python -m app.services.species prepare <txt_emb_species.npy> <txt_emb_species.json> <models dir>")
    prepare(sys.argv[2], sys.argv[3], sys.argv[4])
