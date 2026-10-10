import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from ..config import cache_dir, models_dir
from ..config import face_threshold as env_face_threshold
from ..db import ex, exn, q, q1, setting_get, setting_set
from ..dedup.visual import VIDEO_SAMPLE_POINTS, ffmpeg_path
from . import libraryfs, mediainfo

try:
    import numpy as np
except Exception:
    np = None
try:
    import cv2
except Exception:
    cv2 = None

DETECT_MODEL = "face_detection_yunet_2023mar.onnx"
EMBED_MODEL = "face_recognition_sface_2021dec.onnx"
def face_threshold() -> float:
    stored = setting_get("face_threshold")
    if stored:
        try:
            return float(stored)
        except ValueError:
            pass
    return env_face_threshold()


DETECT_SCORE = 0.72
MIN_FACE_AREA = 0.004
MIN_JOIN_QUALITY = 0.6
MIN_NEW_PERSON_QUALITY = 0.82
EXEMPLAR_K = 10
EXEMPLAR_SLACK = 0.03
MAX_EDGE = 1024
VIDEO_WIDTH = 640

_detector = None
_recognizer = None


def model_paths() -> Tuple[str, str]:
    return os.path.join(models_dir(), DETECT_MODEL), os.path.join(models_dir(), EMBED_MODEL)


def status() -> Dict[str, Any]:
    det, emb = model_paths()
    missing = [os.path.basename(p) for p in (det, emb) if not os.path.isfile(p)]
    return {
        "cv2": cv2 is not None and np is not None,
        "models": not missing,
        "missing_models": missing,
        "ffmpeg": bool(ffmpeg_path()),
        "ready": cv2 is not None and np is not None and not missing,
        "threshold": face_threshold(),
    }


def _engines():
    global _detector, _recognizer
    if _detector is None:
        det, emb = model_paths()
        _detector = cv2.FaceDetectorYN.create(det, "", (320, 320), DETECT_SCORE, 0.3, 5000)
        _recognizer = cv2.FaceRecognizerSF.create(emb, "")
    return _detector, _recognizer


def _load_image_bgr(path: str):
    from . import decode

    pil = decode.open_image(path, path, max_long=MAX_EDGE)
    if pil is None:
        return None
    img = cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
    height, width = img.shape[:2]
    edge = max(width, height)
    if edge > MAX_EDGE:
        scale = MAX_EDGE / edge
        img = cv2.resize(img, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return img


def _video_frames(path: str) -> List[Tuple[float, Any]]:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return []
    width, height, duration, _ = mediainfo.video_meta(path)
    if not width or not height or not duration:
        return []
    out_w = min(VIDEO_WIDTH, width)
    out_h = max(2, round(height * out_w / width / 2) * 2)
    frames: List[Tuple[float, Any]] = []
    points = VIDEO_SAMPLE_POINTS if duration > 1.0 else (0.0,)
    for point in points:
        stamp = max(0.0, min(duration * point, max(0.0, duration - 0.1)))
        try:
            raw = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-noaccurate_seek", "-ss", f"{stamp:.3f}",
                 "-i", path, "-frames:v", "1", "-vf", f"scale={out_w}:{out_h}",
                 "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"],
                capture_output=True, timeout=25, check=True,
            ).stdout
        except Exception:
            continue
        if len(raw) != out_w * out_h * 3:
            continue
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((out_h, out_w, 3)).copy()
        frames.append((stamp, frame))
    return frames


def detect_faces(bgr) -> List[Dict[str, Any]]:
    detector, recognizer = _engines()
    height, width = bgr.shape[:2]
    detector.setInputSize((width, height))
    _, rows = detector.detect(bgr)
    results: List[Dict[str, Any]] = []
    if rows is None:
        return results
    for row in rows:
        rel_w = float(row[2]) / width
        rel_h = float(row[3]) / height
        if rel_w * rel_h < MIN_FACE_AREA:
            continue
        aligned = recognizer.alignCrop(bgr, row)
        feature = recognizer.feature(aligned).flatten().astype(np.float32)
        norm = float(np.linalg.norm(feature)) or 1.0
        feature = feature / norm
        results.append({
            "x": float(row[0]) / width, "y": float(row[1]) / height,
            "w": rel_w, "h": rel_h,
            "quality": float(row[14]),
            "dominance": float(row[14]) * (rel_w * rel_h) ** 0.5,
            "embedding": feature,
        })
    return results


class _Clusterer:
    def __init__(self) -> None:
        self.centroids: Dict[int, Any] = {}
        self.weights: Dict[int, float] = {}
        self.exemplars: Dict[int, list] = {}
        for row in q("SELECT person_id, embedding, quality FROM faces WHERE person_id IS NOT NULL"):
            vec = np.frombuffer(row["embedding"], dtype=np.float32)
            self._absorb(row["person_id"], vec, max(0.1, float(row["quality"])))

    def _absorb(self, pid: int, vec, weight: float) -> None:
        if pid in self.centroids:
            self.centroids[pid] = self.centroids[pid] + vec * weight
            self.weights[pid] += weight
        else:
            self.centroids[pid] = vec * weight
            self.weights[pid] = weight
        bucket = self.exemplars.setdefault(pid, [])
        bucket.append((weight, vec))
        if len(bucket) > EXEMPLAR_K:
            bucket.sort(key=lambda pair: -pair[0])
            del bucket[EXEMPLAR_K:]

    def _exemplar_ok(self, pid: int, embedding, threshold: float) -> bool:
        bucket = self.exemplars.get(pid)
        if not bucket:
            return True
        best = max(float(np.dot(vec, embedding)) for _, vec in bucket)
        return best >= threshold - EXEMPLAR_SLACK

    def assign(self, embedding, weight: float = 1.0) -> Tuple[Optional[int], bool]:
        threshold = face_threshold()
        best_pid, best_cos = 0, -1.0
        for pid, total in self.centroids.items():
            centroid = total / (np.linalg.norm(total) or 1.0)
            cos = float(np.dot(centroid, embedding))
            if cos > best_cos:
                best_pid, best_cos = pid, cos
        weight = max(0.1, weight)
        if best_cos >= threshold and self._exemplar_ok(best_pid, embedding, threshold):
            if weight >= MIN_JOIN_QUALITY:
                self._absorb(best_pid, embedding, weight)
            return best_pid, False
        if weight < MIN_NEW_PERSON_QUALITY:
            return None, False
        pid = ex("INSERT INTO people(name, created_ts) VALUES(NULL, ?)", (time.time(),))
        self._absorb(pid, embedding, weight)
        return pid, True


def scan_job(state: Dict[str, Any]) -> None:
    info = status()
    if not info["ready"]:
        raise RuntimeError("face engine not ready: " + (", ".join(info["missing_models"]) or "opencv/numpy missing"))
    clusterer = _Clusterer()
    counts = {"scanned": 0, "faces": 0, "people_new": 0, "videos": 0, "failed": 0}
    state["counts"] = counts
    rows = q("SELECT id, rel_path, kind FROM media WHERE face_state=0 AND trashed_ts IS NULL AND live_of IS NULL ORDER BY id")
    for row in rows:
        path = libraryfs.abs_path(row["rel_path"])
        frames: List[Tuple[float, Any]] = []
        try:
            if row["kind"] == "image":
                img = _load_image_bgr(path)
                if img is not None:
                    frames = [(0.0, img)]
            else:
                frames = _video_frames(path)
                counts["videos"] += 1
        except Exception:
            frames = []
        if not frames:
            ex("UPDATE media SET face_state=2 WHERE id=?", (row["id"],))
            counts["failed"] += 1
            counts["scanned"] += 1
            continue
        found = 0
        for stamp, frame in frames:
            for face in detect_faces(frame):
                pid, created = clusterer.assign(face["embedding"], face["quality"])
                face_id = ex(
                    "INSERT INTO faces(media_id, frame_ts, x, y, w, h, quality, embedding, person_id) VALUES(?,?,?,?,?,?,?,?,?)",
                    (row["id"], stamp, face["x"], face["y"], face["w"], face["h"], face["quality"],
                     face["embedding"].tobytes(), pid),
                )
                if created:
                    counts["people_new"] += 1
                if pid is not None:
                    refresh_cover(pid, candidate=(face_id, face["dominance"]))
                found += 1
        ex("UPDATE media SET face_state=? WHERE id=?", (1 if found else 2, row["id"]))
        counts["faces"] += found
        counts["scanned"] += 1


def face_crop(face_id: int) -> Optional[str]:
    row = q1(
        "SELECT f.*, m.rel_path, m.kind FROM faces f JOIN media m ON m.id=f.media_id WHERE f.id=?",
        (face_id,),
    )
    if row is None or cv2 is None:
        return None
    folder = os.path.join(cache_dir(), "faces")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, f"{face_id}.jpg")
    if os.path.isfile(out):
        return out
    path = libraryfs.abs_path(row["rel_path"])
    if row["kind"] == "image":
        frame = _load_image_bgr(path)
    else:
        grabbed = [f for f in _video_frames(path) if abs(f[0] - row["frame_ts"]) < 0.5]
        frame = grabbed[0][1] if grabbed else None
    if frame is None:
        return None
    height, width = frame.shape[:2]
    pad = 0.30
    x0 = max(0, int((row["x"] - row["w"] * pad) * width))
    y0 = max(0, int((row["y"] - row["h"] * pad) * height))
    x1 = min(width, int((row["x"] + row["w"] * (1 + pad)) * width))
    y1 = min(height, int((row["y"] + row["h"] * (1 + pad)) * height))
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    edge = max(crop.shape[:2])
    if edge > 384:
        scale = 384 / edge
        crop = cv2.resize(crop, (int(crop.shape[1] * scale), int(crop.shape[0] * scale)))
    cv2.imwrite(out, crop, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return out


def refresh_cover(person_id: int, candidate: Optional[Tuple[int, float]] = None) -> None:
    locked = q1("SELECT cover_locked FROM people WHERE id=?", (person_id,))
    if locked is not None and locked["cover_locked"]:
        return
    best = candidate
    for row in q("SELECT id, quality, w, h FROM faces WHERE person_id=?", (person_id,)):
        dom = float(row["quality"]) * (max(0.0, float(row["w"]) * float(row["h"])) ** 0.5)
        if best is None or dom > best[1]:
            best = (row["id"], dom)
    if best:
        ex("UPDATE people SET cover_face_id=? WHERE id=?", (best[0], person_id))


def unassign_face(face_id: int) -> Optional[int]:
    row = q1("SELECT person_id FROM faces WHERE id=?", (face_id,))
    if row is None or row["person_id"] is None:
        return None
    pid = row["person_id"]
    ex("UPDATE faces SET person_id=NULL WHERE id=?", (face_id,))
    remaining = q1("SELECT COUNT(*) AS n FROM faces WHERE person_id=?", (pid,))
    if remaining["n"] == 0:
        ex("DELETE FROM people WHERE id=?", (pid,))
        return None
    refresh_cover(pid)
    return pid


def merge_people(into_id: int, from_ids) -> int:
    moved = 0
    for pid in from_ids:
        if pid == into_id:
            continue
        moved += exn("UPDATE faces SET person_id=? WHERE person_id=?", (into_id, pid))
        ex("DELETE FROM people WHERE id=?", (pid,))
    refresh_cover(into_id)
    return moved


def delete_person(person_id: int) -> None:
    ex("UPDATE faces SET person_id=NULL WHERE person_id=?", (person_id,))
    ex("DELETE FROM people WHERE id=?", (person_id,))


def assign_face(face_id: int, person_id: Optional[int], new_name: Optional[str] = None) -> int:
    row = q1("SELECT person_id FROM faces WHERE id=?", (face_id,))
    if row is None:
        raise ValueError("no such face")
    old_pid = row["person_id"]
    if person_id is None:
        person_id = ex("INSERT INTO people(name, created_ts) VALUES(?, ?)", (new_name, time.time()))
    ex("UPDATE faces SET person_id=? WHERE id=?", (person_id, face_id))
    if old_pid is not None and old_pid != person_id:
        remaining = q1("SELECT COUNT(*) AS n FROM faces WHERE person_id=?", (old_pid,))
        if remaining["n"] == 0:
            ex("DELETE FROM people WHERE id=?", (old_pid,))
        else:
            refresh_cover(old_pid)
    refresh_cover(person_id)
    return person_id


def rebuild_people(threshold: Optional[float] = None) -> Dict[str, int]:
    if threshold is not None:
        setting_set("face_threshold", str(threshold))
    anchors: Dict[int, list] = {}
    for named in q("SELECT id FROM people WHERE name IS NOT NULL"):
        rows = q(
            "SELECT embedding, quality FROM faces WHERE person_id=? ORDER BY quality DESC LIMIT ?",
            (named["id"], EXEMPLAR_K),
        )
        anchors[named["id"]] = [
            (max(0.1, float(r["quality"])), np.frombuffer(r["embedding"], dtype=np.float32)) for r in rows
        ]
    ex("UPDATE faces SET person_id=NULL")
    ex("DELETE FROM people WHERE name IS NULL")
    clusterer = _Clusterer()
    for pid, pairs in anchors.items():
        for weight, vec in pairs:
            clusterer._absorb(pid, vec, weight)
    rows = q("SELECT id, embedding, quality FROM faces ORDER BY quality DESC")
    assigned = created_count = 0
    for row in rows:
        vec = np.frombuffer(row["embedding"], dtype=np.float32)
        pid, created = clusterer.assign(vec, float(row["quality"]))
        if pid is None:
            continue
        ex("UPDATE faces SET person_id=? WHERE id=?", (pid, row["id"]))
        assigned += 1
        if created:
            created_count += 1
    for person in q("SELECT id FROM people"):
        refresh_cover(person["id"])
    kept = q1("SELECT COUNT(*) AS n FROM people WHERE name IS NOT NULL")["n"]
    return {"faces_assigned": assigned, "people": created_count + kept, "named_preserved": kept}
