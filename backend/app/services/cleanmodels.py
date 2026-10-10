import os
import threading
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from ..config import models_dir

SAM_MODEL = "image_segmentation_efficientsam_ti_2025april.onnx"
DET_MODEL = "object_detection_yolox_2022nov.onnx"
FACE_MODEL = "face_detection_yunet_2023mar.onnx"
SAM_SIZE = 1024
DET_SIZE = 640
MAX_POINTS = 6
DET_SCORE = 0.45
NMS = 0.5
SUBJECT_AREA = 0.15
MAX_AREA = 0.5
COCO = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light", "fire hydrant",
    "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut",
    "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
)

_lock = threading.Lock()
_sessions: Dict[str, Any] = {}


def _path(name: str) -> str:
    return os.path.join(models_dir(), name)


def status() -> Dict[str, bool]:
    try:
        import onnxruntime  # noqa: F401
        runtime = True
    except Exception:
        runtime = False
    return {"segment": runtime and os.path.isfile(_path(SAM_MODEL)), "suggest": runtime and os.path.isfile(_path(DET_MODEL)),
            "faces": os.path.isfile(_path(FACE_MODEL))}


def _session(name: str):
    with _lock:
        sess = _sessions.get(name)
        if sess is None:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) - 1))
            sess = ort.InferenceSession(_path(name), sess_options=opts, providers=["CPUExecutionProvider"])
            _sessions[name] = sess
        return sess


def _polygons(mask: np.ndarray, w: int, h: int) -> List[List[List[float]]]:
    import cv2

    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    min_area = mask.shape[0] * mask.shape[1] * 0.0005
    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue
        approx = cv2.approxPolyDP(contour, 0.0015 * max(mask.shape), True)
        out.append([[round(float(p[0][0]) / w, 5), round(float(p[0][1]) / h, 5)] for p in approx][:600])
    return out[:12]


def segment(rgb: np.ndarray, points: Sequence[Sequence[float]] = (), box: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    import cv2

    h, w = rgb.shape[:2]
    img = cv2.resize(rgb, (SAM_SIZE, SAM_SIZE), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    coords = np.zeros((MAX_POINTS, 2), np.float32)
    labels = np.full((MAX_POINTS,), -1.0, np.float32)
    i = 0
    if box is not None:
        x, y, bw, bh = box
        coords[0] = (x * SAM_SIZE, y * SAM_SIZE)
        coords[1] = ((x + bw) * SAM_SIZE, (y + bh) * SAM_SIZE)
        labels[0], labels[1] = 2, 3
        i = 2
    for px, py in list(points)[: MAX_POINTS - i]:
        coords[i] = (px * SAM_SIZE, py * SAM_SIZE)
        labels[i] = 1
        i += 1
    if i == 0:
        return {"polygons": [], "area": 0.0}
    masks, ious = _session(SAM_MODEL).run(["output_masks", "iou_predictions"], {
        "batched_images": img.transpose(2, 0, 1)[None], "batched_point_coords": coords[None, None], "batched_point_labels": labels[None, None]})
    best = int(np.argmax(ious[0, 0]))
    if box is None:
        areas = [float((masks[0, 0, k] >= 0).mean()) for k in range(masks.shape[2])]
        fits = [k for k in range(len(areas)) if areas[k] <= MAX_AREA and float(ious[0, 0, k]) >= 0.3]
        best = max(fits, key=lambda k: areas[k]) if fits else best
    mask = masks[0, 0, best] >= 0
    area = float(mask.mean())
    return {"polygons": _polygons(mask, SAM_SIZE, SAM_SIZE), "area": round(area, 5), "iou": round(float(ious[0, 0, best]), 3)}


def suggest(rgb: np.ndarray) -> List[Dict[str, Any]]:
    import cv2

    h, w = rgb.shape[:2]
    scale = min(DET_SIZE / h, DET_SIZE / w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    canvas = np.full((DET_SIZE, DET_SIZE, 3), 114, np.uint8)
    canvas[:nh, :nw] = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), (nw, nh), interpolation=cv2.INTER_LINEAR)
    out = _session(DET_MODEL).run(None, {"images": canvas.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    grids, strides = [], []
    for stride in (8, 16, 32):
        size = DET_SIZE // stride
        xv, yv = np.meshgrid(np.arange(size), np.arange(size))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((size * size, 1), stride))
    grid, stride = np.concatenate(grids), np.concatenate(strides)
    xy = (out[:, :2] + grid) * stride
    wh = np.exp(out[:, 2:4]) * stride
    scores = out[:, 4:5] * out[:, 5:]
    cls = scores.argmax(1)
    best = scores.max(1)
    keep = best >= DET_SCORE
    boxes = np.concatenate([xy - wh / 2, wh], 1)[keep] / scale
    idx = cv2.dnn.NMSBoxes(boxes.tolist(), best[keep].tolist(), DET_SCORE, NMS)
    found = []
    for k in (np.array(idx).reshape(-1) if len(idx) else []):
        x, y, bw, bh = (float(v) for v in boxes[k])
        x0, y0 = max(0.0, x / w), max(0.0, y / h)
        x1, y1 = min(1.0, (x + bw) / w), min(1.0, (y + bh) / h)
        if x1 <= x0 or y1 <= y0:
            continue
        found.append({"box": [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)],
                      "label": COCO[int(cls[keep][k])], "score": round(float(best[keep][k]), 3)})
    if not found:
        return []
    def area(f):
        return f["box"][2] * f["box"][3]
    def central(f):
        cx, cy = f["box"][0] + f["box"][2] / 2, f["box"][1] + f["box"][3] / 2
        return abs(cx - 0.5) < 0.25 and abs(cy - 0.5) < 0.3
    subject = max(found, key=area)
    out_list = [f for f in found if area(f) <= MAX_AREA and not (f is subject and area(f) >= SUBJECT_AREA and central(f))]
    return sorted(out_list, key=lambda f: -f["score"])[:20]


def faces(rgb: np.ndarray) -> List[List[float]]:
    import cv2

    if not os.path.isfile(_path(FACE_MODEL)):
        return []
    h, w = rgb.shape[:2]
    det = cv2.FaceDetectorYN.create(_path(FACE_MODEL), "", (w, h), 0.7, 0.3, 5000)
    _, found = det.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    out = []
    for f in (found if found is not None else []):
        x, y, bw, bh = (float(v) for v in f[:4])
        out.append([round(max(0.0, x / w), 4), round(max(0.0, y / h), 4), round(bw / w, 4), round(bh / h, 4)])
    return out


def pixelate(a: np.ndarray, box: Sequence[float]) -> None:
    import cv2

    h, w = a.shape[:2]
    x0, y0 = int(max(0, box[0] * w)), int(max(0, box[1] * h))
    x1, y1 = int(min(w, (box[0] + box[2]) * w)), int(min(h, (box[1] + box[3]) * h))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    region = a[y0:y1, x0:x1]
    cells = max(4, min(12, (x1 - x0) // 12))
    small = cv2.resize(region, (cells, max(4, int(cells * (y1 - y0) / (x1 - x0)))), interpolation=cv2.INTER_AREA)
    a[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)


def fill_polygons(mask: np.ndarray, polygons: Sequence[Sequence[Sequence[float]]], grow: int) -> None:
    import cv2

    h, w = mask.shape[:2]
    pts = []
    for poly in polygons[:12]:
        arr = np.array([[float(p[0]) * w, float(p[1]) * h] for p in poly[:600]], dtype=np.int32)
        if len(arr) >= 3:
            pts.append(arr)
    if pts:
        own = np.zeros_like(mask)
        cv2.fillPoly(own, pts, 255)
        if grow > 0:
            own = cv2.dilate(own, np.ones((3, 3), np.uint8), iterations=grow)
        np.maximum(mask, own, out=mask)
