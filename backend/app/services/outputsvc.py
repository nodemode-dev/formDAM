import io
import json
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from ..db import ex, q1
from . import decode, editsvc, filesvc, keywordsvc, renamesvc, xmpsvc

FORMATS = {"jpeg": ("JPEG", ".jpg"), "png": ("PNG", ".png"), "tiff": ("TIFF", ".tif"), "webp": ("WEBP", ".webp"), "heic": ("HEIF", ".heic")}
PAGES = {"a4": (2480, 3508), "letter": (2550, 3300), "a3": (3508, 4961), "tabloid": (3300, 5100)}
DEFAULT_EXPORT: Dict[str, Any] = {
    "format": "jpeg", "quality": 90, "size": "full", "px": 2048, "naming": "{name}", "subfolder": "none",
    "metadata": "all", "location": True, "sidecar": False, "original": False,
}


def _target_size(w: int, h: int, opts: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    mode = opts.get("size", "full")
    px = int(opts.get("px") or 2048)
    if mode == "long" and max(w, h) > px:
        s = px / max(w, h)
    elif mode == "short" and min(w, h) > px:
        s = px / min(w, h)
    elif mode == "width" and w > px:
        s = px / w
    elif mode == "height" and h > px:
        s = px / h
    else:
        return None
    return max(1, round(w * s)), max(1, round(h * s))


def _subfolder(row, opts: Dict[str, Any]) -> str:
    mode = opts.get("subfolder", "none")
    if mode == "date" and row["created_ts"]:
        return datetime.fromtimestamp(row["created_ts"]).strftime("%Y/%Y-%m-%d")
    if mode == "month" and row["created_ts"]:
        return datetime.fromtimestamp(row["created_ts"]).strftime("%Y/%m")
    if mode == "place":
        return renamesvc.safe(row["place"] or row["country"] or "No Place")
    if mode == "album":
        album = q1("""SELECT a.name FROM albums a JOIN album_items ai ON ai.album_id=a.id
                      WHERE ai.media_id=? AND a.is_private=0 ORDER BY a.id LIMIT 1""", (row["id"],))
        return renamesvc.safe(album["name"]) if album else "No Album"
    return ""


def _exif_bytes(src: Any, row, opts: Dict[str, Any]) -> Optional[bytes]:
    if opts.get("metadata") == "none":
        return None
    try:
        with Image.open(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src) as orig:
            exif = orig.getexif()
    except Exception:
        return None
    exif[0x0112] = 1
    if opts.get("metadata") == "copyright":
        keep = {0x8298, 0x013B}
        for tag in list(exif.keys()):
            if tag not in keep:
                del exif[tag]
    if not opts.get("location", True) or row["location_hidden"]:
        try:
            del exif[0x8825]
        except KeyError:
            pass
    try:
        return exif.tobytes()
    except Exception:
        return None


def _xmp_packet(row, opts: Dict[str, Any]) -> Optional[str]:
    if opts.get("metadata") == "none":
        return None
    rec = xmpsvc.record_for(row["id"], include_location=bool(opts.get("location", True)))
    if rec is None:
        return None
    if opts.get("metadata") == "copyright":
        meta = rec.get("meta") or {}
        rec = {"rating": 0, "meta": {k: meta[k] for k in ("creator", "copyright", "copyrightStatus", "rightsUsage", "copyrightUrl") if meta.get(k)}}
    rec.pop("edit", None)
    return xmpsvc.build_xmp(rec)


def export_one(row, dest: str, seq: int, opts: Dict[str, Any], taken: set) -> Optional[str]:
    from ..routers.render import source_of

    src, _ = source_of(row)
    if src is None:
        return None
    folder = os.path.join(dest, _subfolder(row, opts))
    os.makedirs(folder, exist_ok=True)
    base = renamesvc.safe(renamesvc.expand(opts.get("naming") or "{name}", dict(row), seq, opts.get("custom", "")))
    if opts.get("original") or row["kind"] != "image":
        ext = os.path.splitext(row["name"])[1]
        target = filesvc._unique(os.path.join(folder, base + ext), taken)
        if isinstance(src, (bytes, bytearray)):
            with open(target, "wb") as fh:
                fh.write(src)
        else:
            shutil.copy2(src, target)
        if opts.get("sidecar"):
            packet = _xmp_packet(row, opts)
            if packet:
                with open(os.path.splitext(target)[0] + ".xmp", "w", encoding="utf-8") as fh:
                    fh.write(packet)
        return target
    fmt, ext = FORMATS.get(opts.get("format", "jpeg"), FORMATS["jpeg"])
    img = editsvc.render_still(row["id"], src, None) or decode.open_image(src, row["name"], max_long=None, develop=True)
    if img is None:
        return None
    size = _target_size(img.width, img.height, opts)
    if size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    if fmt in ("JPEG", "HEIF") or img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    target = filesvc._unique(os.path.join(folder, base + ext), taken)
    quality = int(opts.get("quality") or 90)
    kwargs: Dict[str, Any] = {}
    exif = _exif_bytes(src, row, opts)
    if exif and fmt in ("JPEG", "WEBP", "PNG", "TIFF", "HEIF"):
        kwargs["exif"] = exif
    if fmt == "JPEG":
        kwargs.update(quality=quality, optimize=True, subsampling=0 if quality >= 90 else 2)
    elif fmt == "WEBP":
        kwargs.update(quality=quality, method=5)
    elif fmt == "HEIF":
        from .. import mediacodecs

        mediacodecs.register()
        kwargs.update(quality=quality)
    elif fmt == "TIFF":
        kwargs.update(compression="tiff_lzw")
    packet = _xmp_packet(row, opts)
    if packet and fmt in ("PNG", "WEBP", "TIFF", "HEIF"):
        kwargs["xmp"] = packet.encode("utf-8")
    img.save(target, fmt, **kwargs)
    if packet and fmt == "JPEG":
        try:
            xmpsvc.write_jpeg_xmp(target, packet)
        except (OSError, ValueError):
            pass
    if opts.get("sidecar") and packet:
        with open(os.path.splitext(target)[0] + ".xmp", "w", encoding="utf-8") as fh:
            fh.write(packet)
    return target


def export_job(ids: List[int], dest: str, opts: Dict[str, Any], state: Dict[str, Any]) -> None:
    from .. import vaultcrypt

    merged = {**DEFAULT_EXPORT, **(opts or {})}
    os.makedirs(dest, exist_ok=True)
    counts = {"exported": 0, "skipped": 0, "total": len(ids)}
    state["counts"] = counts
    state["dest"] = dest
    taken: set = set()
    for seq, media_id in enumerate(ids, 1):
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        if row is None or row["trashed_ts"] is not None or (vaultcrypt.protected(row) and not merged.get("allow_private")):
            counts["skipped"] += 1
            continue
        try:
            done = export_one(row, dest, seq, merged, taken)
        except Exception:
            done = None
        counts["exported" if done else "skipped"] += 1


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def contact_sheet(ids: List[int], opts: Dict[str, Any]) -> bytes:
    from ..routers.render import source_of

    page_w, page_h = PAGES.get(opts.get("page", "a4"), PAGES["a4"])
    if opts.get("landscape"):
        page_w, page_h = page_h, page_w
    cols = max(1, min(10, int(opts.get("columns") or 4)))
    captions = opts.get("captions", "name")
    title = str(opts.get("title") or "")
    margin = int(page_w * 0.05)
    gap = int(page_w * 0.015)
    head = int(page_h * 0.05) if title else 0
    cell = (page_w - 2 * margin - (cols - 1) * gap) // cols
    cap_h = int(cell * 0.14) if captions != "none" else 0
    rows = max(1, (page_h - 2 * margin - head + gap) // (cell + cap_h + gap))
    per_page = cols * rows
    pages: List[Image.Image] = []
    font = _font(max(14, cap_h // 2))
    title_font = _font(max(24, head // 2))
    for start in range(0, len(ids), per_page):
        page = Image.new("RGB", (page_w, page_h), "white")
        draw = ImageDraw.Draw(page)
        if title:
            draw.text((margin, margin), title, fill="black", font=title_font)
        for i, media_id in enumerate(ids[start:start + per_page]):
            row = q1("SELECT * FROM media WHERE id=?", (media_id,))
            if row is None:
                continue
            x = margin + (i % cols) * (cell + gap)
            y = margin + head + (i // cols) * (cell + cap_h + gap)
            img = None
            from . import thumbs

            path = thumbs.ensure_thumb(media_id, row["rel_path"], row["kind"], 768)
            if path:
                try:
                    img = Image.open(path).convert("RGB")
                except Exception:
                    img = None
            if img is None and row["kind"] == "image":
                src, _ = source_of(row)
                img = editsvc.render_still(media_id, src, cell) or decode.open_image(src, row["name"], max_long=cell) if src else None
            if img is not None:
                img.thumbnail((cell, cell), Image.Resampling.LANCZOS)
                page.paste(img.convert("RGB"), (x + (cell - img.width) // 2, y + (cell - img.height) // 2))
            else:
                draw.rectangle((x, y, x + cell, y + cell), outline="#999")
            if captions != "none":
                label = row["title"] if captions == "title" and row["title"] else row["name"]
                if captions == "date" and row["created_ts"]:
                    label = datetime.fromtimestamp(row["created_ts"]).strftime("%Y-%m-%d %H:%M")
                draw.text((x, y + cell + 4), str(label)[:60], fill="#333", font=font)
        pages.append(page)
    if not pages:
        pages = [Image.new("RGB", (page_w, page_h), "white")]
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=300.0, save_all=True, append_images=pages[1:])
    return buf.getvalue()


def print_sheet(ids: List[int], opts: Dict[str, Any]) -> bytes:
    from ..routers.render import source_of

    page_w, page_h = PAGES.get(opts.get("page", "letter"), PAGES["letter"])
    margin = int(page_w * float(opts.get("margin", 0.05)))
    pages = []
    for media_id in ids:
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        if row is None or row["kind"] != "image":
            continue
        src, _ = source_of(row)
        if src is None:
            continue
        img = editsvc.render_still(media_id, src, max(page_w, page_h)) or decode.open_image(src, row["name"], max_long=max(page_w, page_h), develop=True)
        if img is None:
            continue
        pw, ph = (page_h, page_w) if img.width > img.height else (page_w, page_h)
        page = Image.new("RGB", (pw, ph), "white")
        fit = img.convert("RGB")
        fit.thumbnail((pw - 2 * margin, ph - 2 * margin), Image.Resampling.LANCZOS)
        page.paste(fit, ((pw - fit.width) // 2, (ph - fit.height) // 2))
        pages.append(page)
    if not pages:
        pages = [Image.new("RGB", (page_w, page_h), "white")]
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=300.0, save_all=True, append_images=pages[1:])
    return buf.getvalue()


STEP_KINDS = ("template", "keywords", "rating", "label", "rename", "export", "sidecar")


def run_workflow(steps: List[Dict[str, Any]], ids: List[int], state: Dict[str, Any]) -> None:
    counts: Dict[str, Any] = {"steps": 0, "items": len(ids)}
    state["counts"] = counts
    for step in steps:
        kind = step.get("kind")
        if kind == "template":
            tpl = q1("SELECT fields_json FROM metadata_templates WHERE id=?", (int(step.get("template_id") or 0),))
            if tpl:
                apply_fields(ids, json.loads(tpl["fields_json"]), step.get("mode", "fill"))
        elif kind == "keywords":
            keywordsvc.assign(ids, [str(k) for k in step.get("add") or []], [])
        elif kind == "rating":
            ex(f"UPDATE media SET rating=?, xmp_ts=NULL WHERE id IN ({','.join('?' * len(ids))})", (int(step.get("value") or 0), *ids))
        elif kind == "label":
            ex(f"UPDATE media SET label=?, xmp_ts=NULL WHERE id IN ({','.join('?' * len(ids))})", (step.get("value") or None, *ids))
        elif kind == "rename" and step.get("template"):
            filesvc.rename(ids, str(step["template"]), int(step.get("start") or 1), str(step.get("custom") or ""))
        elif kind == "sidecar":
            for media_id in ids:
                xmpsvc.write_sidecar(media_id)
        elif kind == "export" and step.get("dest"):
            sub: Dict[str, Any] = {}
            export_job(ids, str(step["dest"]), step.get("options") or {}, sub)
            counts["exported"] = sub.get("counts", {}).get("exported", 0)
        counts["steps"] += 1


def apply_fields(ids: List[int], fields: Dict[str, Any], mode: str = "replace") -> int:
    direct = {"title": "title", "caption": "caption", "altText": "alt_text"}
    changed = 0
    for media_id in ids:
        row = q1("SELECT title, caption, alt_text, iptc_json FROM media WHERE id=?", (media_id,))
        if row is None:
            continue
        iptc = xmpsvc.iptc_of(row)
        sets, params = [], []
        for key, value in fields.items():
            if key in direct:
                col = direct[key]
                if mode == "fill" and row[col]:
                    continue
                sets.append(f"{col}=?")
                params.append(value or None)
            elif key in xmpsvc.FIELDS:
                if mode == "fill" and iptc.get(key):
                    continue
                if value in (None, ""):
                    iptc.pop(key, None)
                else:
                    iptc[key] = value
        sets += ["iptc_json=?", "xmp_ts=NULL"]
        params.append(json.dumps(iptc) if iptc else None)
        ex(f"UPDATE media SET {', '.join(sets)} WHERE id=?", (*params, media_id))
        changed += 1
    return changed
