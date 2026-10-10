from typing import Any, Dict, List, Optional, Tuple

import numpy as np

HIGHLIGHTS = {"clip": 0, "blend": 2, "rebuild": 5}
TEMP_RANGE = (2000.0, 12000.0)


def _xy(temp: float) -> Tuple[float, float]:
    t = max(1667.0, min(25000.0, temp))
    if t <= 4000:
        x = -0.2661239e9 / t ** 3 - 0.2343589e6 / t ** 2 + 0.8776956e3 / t + 0.179910
    else:
        x = -3.0258469e9 / t ** 3 + 2.1070379e6 / t ** 2 + 0.2226347e3 / t + 0.240390
    if t <= 2222:
        y = -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - 0.20219683
    elif t <= 4000:
        y = -0.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x ** 3 - 5.87338670 * x ** 2 + 3.75112997 * x - 0.37001483
    return x, y


def _matrix(raw) -> Optional[np.ndarray]:
    try:
        m = np.asarray(raw.rgb_xyz_matrix, dtype=np.float64)[:3]
    except Exception:
        return None
    return m if m.shape == (3, 3) and np.abs(m).sum() > 1e-6 else None


def multipliers(raw, temp: float, tint: float = 0.0) -> Optional[List[float]]:
    m = _matrix(raw)
    if m is None:
        return None
    x, y = _xy(temp)
    xyz = np.array([x / y, 1.0, (1 - x - y) / y])
    cam = m @ xyz
    if np.any(cam <= 1e-9):
        return None
    mul = 1.0 / cam
    mul = mul / mul[1]
    green = 1.0 - max(-100.0, min(100.0, tint)) / 250.0
    return [float(mul[0]), float(green), float(mul[2]), float(green)]


def as_shot(raw) -> Dict[str, Any]:
    try:
        cam = [float(v) for v in raw.camera_whitebalance[:3]]
    except Exception:
        return {"temp": 5500, "tint": 0, "kelvin": False}
    if _matrix(raw) is None or cam[1] <= 0:
        return {"temp": 5500, "tint": 0, "kelvin": False}
    target = np.log(np.array([cam[0] / cam[1], cam[2] / cam[1]]))
    best, best_tint, best_err = 5500.0, 0.0, 1e9
    for temp in np.arange(TEMP_RANGE[0], TEMP_RANGE[1] + 1, 50.0):
        base = multipliers(raw, float(temp))
        if base is None:
            continue
        for tint in np.arange(-100.0, 101.0, 2.0):
            green = 1.0 - tint / 250.0
            got = np.log(np.array([base[0] / green, base[2] / green]))
            err = float(np.sum((got - target) ** 2))
            if err < best_err:
                best, best_tint, best_err = float(temp), float(tint), err
    return {"temp": int(round(best / 10) * 10), "tint": int(best_tint), "kelvin": True}


def params(raw, opts: Dict[str, Any]) -> Dict[str, Any]:
    import rawpy

    out: Dict[str, Any] = {"use_camera_wb": True}
    wb = str(opts.get("wb") or "camera")
    if wb == "auto":
        out = {"use_auto_wb": True}
    elif wb == "daylight":
        out = {"use_camera_wb": False}
    elif wb == "kelvin":
        mul = multipliers(raw, float(opts.get("temp") or 5500), float(opts.get("tint") or 0))
        out = {"user_wb": mul} if mul else {"use_camera_wb": True}
    hl = HIGHLIGHTS.get(str(opts.get("highlights") or "clip"), 0)
    if hl:
        out["highlight_mode"] = hl
    if opts.get("demosaic") == "quality":
        out["demosaic_algorithm"] = rawpy.DemosaicAlgorithm.DHT
    elif opts.get("demosaic") == "fast":
        out["demosaic_algorithm"] = rawpy.DemosaicAlgorithm.LINEAR
    noise = float(opts.get("noise") or 0)
    if noise > 0:
        out["noise_thr"] = noise * 1000.0
        out["fbdd_noise_reduction"] = rawpy.FBDDNoiseReductionMode.Full if noise > 0.5 else rawpy.FBDDNoiseReductionMode.Light
    ca_r, ca_b = float(opts.get("ca_red") or 0), float(opts.get("ca_blue") or 0)
    if ca_r or ca_b:
        out["chromatic_aberration"] = (1.0 + ca_r * 0.01, 1.0 + ca_b * 0.01)
    return out


def develop(raw, opts: Dict[str, Any], half: bool) -> np.ndarray:
    lin = raw.postprocess(output_bps=16, half_size=half, gamma=(1, 1), no_auto_bright=True, **params(raw, opts)).astype(np.float32) / 65535.0
    ref = float(np.percentile(lin, 99.0))
    scale = (2.0 ** max(-3.0, min(3.0, float(opts.get("exposure") or 0)))) / max(ref, 1e-4)
    v = lin * scale
    if str(opts.get("highlights") or "clip") != "clip":
        knee = 0.8
        v = np.where(v > knee, knee + (1 - knee) * (1 - np.exp(-(v - knee) / (1 - knee))), v)
    v = np.clip(v, 0.0, 1.0)
    out = np.where(v < 0.018, v * 4.5, 1.099 * np.power(v, 0.45) - 0.099)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
