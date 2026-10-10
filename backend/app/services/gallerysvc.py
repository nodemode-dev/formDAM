import hashlib
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from ..config import cache_dir
from ..db import q1
from . import thumbs

SHAREABLE = "m.trashed_ts IS NULL AND m.private=0 AND m.hidden=0 AND m.live_of IS NULL"


def _shareable_ids(ids: List[int]) -> List[int]:
    from .. import vaultcrypt

    out = []
    for media_id in ids:
        row = q1(f"SELECT m.* FROM media m WHERE m.id=? AND {SHAREABLE}", (media_id,))
        if row is None or vaultcrypt.protected(row) or vaultcrypt.is_vaulted(media_id):
            continue
        out.append(media_id)
    return out



def download_path(share, media_id: int) -> Optional[str]:
    from . import libraryfs

    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    src = libraryfs.abs_path(row["rel_path"])
    trimmed = row["kind"] == "video" and (row["trim_in"] is not None or row["trim_out"] is not None)
    if share["include_location"] and not row["location_hidden"] and not row["edit_json"] and not trimmed:
        return src
    folder = os.path.join(cache_dir(), "share")
    os.makedirs(folder, exist_ok=True)
    stamp = hashlib.sha1(f"{row['edit_json'] or ''}|{row['edited_ts'] or 0}|{share['include_location']}|{row['trim_in']}|{row['trim_out']}".encode()).hexdigest()[:12]
    if row["kind"] == "video":
        out = os.path.join(folder, f"{media_id}_{stamp}{os.path.splitext(row['name'])[1].lower() or '.mp4'}")
        if not os.path.isfile(out):
            from ..dedup.visual import ffmpeg_path

            ff = ffmpeg_path()
            if not ff:
                return None
            tmp = out + ".part" + os.path.splitext(out)[1]
            args = [ff, "-y", "-v", "error"]
            if row["trim_in"] is not None:
                args += ["-ss", f"{float(row['trim_in']):.3f}"]
            if row["trim_out"] is not None:
                args += ["-to", f"{float(row['trim_out']):.3f}"]
            args += ["-i", src, "-map", "0:v:0", "-map", "0:a?", "-dn", "-c", "copy"]
            if not share["include_location"]:
                args += ["-map_metadata", "-1"]
            done = subprocess.run(args + [tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
            if done.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                return None
            os.replace(tmp, out)
        return out
    out = os.path.join(folder, f"{media_id}_{stamp}.jpg")
    if not os.path.isfile(out):
        from ..routers.render import render_image

        img, _ = render_image(row, 100000)
        if img is None:
            return None
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".jpg")
        os.close(fd)
        exif = gps_exif(row) if share["include_location"] else None
        if exif is not None:
            img.convert("RGB").save(tmp, "JPEG", quality=92, exif=exif)
        else:
            img.convert("RGB").save(tmp, "JPEG", quality=92)
        os.replace(tmp, out)
    return out


def gps_exif(row):
    if row["lat"] is None or row["lon"] is None or row["location_hidden"]:
        return None
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational

    def dms(value: float):
        value = abs(value)
        deg = int(value)
        minutes = int((value - deg) * 60)
        seconds = round(((value - deg) * 60 - minutes) * 60 * 1000)
        return (IFDRational(deg, 1), IFDRational(minutes, 1), IFDRational(seconds, 1000))

    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    gps[1] = "N" if row["lat"] >= 0 else "S"
    gps[2] = dms(row["lat"])
    gps[3] = "E" if row["lon"] >= 0 else "W"
    gps[4] = dms(row["lon"])
    return exif


def web_gallery(ids: List[int], title: str, dest: str, include_location: bool, state: Dict[str, Any]) -> None:
    import json
    import re
    import shutil

    from ..routers.render import render_image

    name = re.sub(r"[^\w .-]+", "", title).strip() or "Web Gallery"
    folder = os.path.join(dest, name)
    n = 1
    while os.path.exists(folder):
        n += 1
        folder = os.path.join(dest, f"{name} {n}")
    os.makedirs(os.path.join(folder, "photos"))
    os.makedirs(os.path.join(folder, "thumbs"))
    ok = _shareable_ids(ids)
    counts = {"written": 0, "skipped": len(ids) - len(ok)}
    state["counts"] = counts
    state["dest"] = folder
    fake = {"include_location": int(include_location), "allow_download": 1}
    entries = []
    for pos, media_id in enumerate(ok, start=1):
        row = q1("SELECT * FROM media WHERE id=?", (media_id,))
        stem = f"{pos:04d}"
        if row["kind"] == "video":
            src = download_path(fake, media_id)
            if src is None:
                counts["skipped"] += 1
                continue
            full = f"photos/{stem}{os.path.splitext(src)[1]}"
            shutil.copy2(src, os.path.join(folder, full))
            thumb = thumbs.ensure_thumb(media_id, row["rel_path"], "video", 768)
            if thumb:
                from PIL import Image

                Image.open(thumb).convert("RGB").save(os.path.join(folder, f"thumbs/{stem}.jpg"), "JPEG", quality=85)
        else:
            img, _ = render_image(row, 2048)
            if img is None:
                counts["skipped"] += 1
                continue
            full = f"photos/{stem}.jpg"
            exif = gps_exif(row) if include_location else None
            if exif is not None:
                img.convert("RGB").save(os.path.join(folder, full), "JPEG", quality=90, exif=exif)
            else:
                img.convert("RGB").save(os.path.join(folder, full), "JPEG", quality=90)
            img.thumbnail((640, 640))
            img.convert("RGB").save(os.path.join(folder, f"thumbs/{stem}.jpg"), "JPEG", quality=82)
        entries.append({"full": full, "thumb": f"thumbs/{stem}.jpg", "kind": row["kind"], "title": row["title"] or "", "caption": row["caption"] or ""})
        counts["written"] += 1
    data = json.dumps({"title": title, "items": entries}).replace("</", "<\\/")
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(GALLERY.replace("{{title}}", html_escape(title)).replace("{{data}}", data))


def html_escape(text: str) -> str:
    import html

    return html.escape(text or "")


GALLERY = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{title}}</title>
<style>
:root { --bg: #0d0d0f; --panel: #17171a; --text: #f2f2f4; --muted: #a0a0a8; --layer-viewer: 10; color-scheme: dark; }
@media (prefers-color-scheme: light) { :root { --bg: #f6f6f7; --panel: #ffffff; --text: #18181b; --muted: #5d5d66; color-scheme: light; } }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 22px; margin: 20px 16px 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 4px; padding: 0 16px 40px; }
.grid a { display: block; aspect-ratio: 1; background: var(--panel); overflow: hidden; border-radius: 4px; }
.grid img { width: 100%; height: 100%; object-fit: cover; display: block; }
.view { position: fixed; inset: 0; z-index: var(--layer-viewer); background: rgba(0,0,0,.94); display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 8px; }
.view[hidden] { display: none; }
.view img, .view video { max-width: 96vw; max-height: 86vh; object-fit: contain; }
.view p { color: #ddd; margin: 0; max-width: 90vw; text-align: center; }
.view button { position: absolute; top: 12px; font: inherit; padding: 6px 12px; border-radius: 999px; border: 1px solid #444; background: #1b1b1e; color: #eee; cursor: pointer; }
.close { right: 12px; } .prev { left: 12px; } .next { left: 100px; }
</style></head><body>
<h1>{{title}}</h1><div class="grid" id="grid"></div>
<div class="view" id="view" hidden><button class="prev" type="button">Previous</button><button class="next" type="button">Next</button><button class="close" type="button">Close</button><div id="stage"></div><p id="cap"></p></div>
<script>
const D = {{data}};
const grid = document.getElementById("grid"), view = document.getElementById("view"), stage = document.getElementById("stage"), cap = document.getElementById("cap");
let at = -1;
D.items.forEach((it, i) => { const a = document.createElement("a"); a.href = it.full; const img = document.createElement("img"); img.src = it.thumb; img.alt = it.title; img.loading = "lazy"; a.append(img); a.onclick = (e) => { e.preventDefault(); show(i); }; grid.append(a); });
function show(i) { if (i < 0 || i >= D.items.length) return; at = i; const it = D.items[i]; const m = document.createElement(it.kind === "video" ? "video" : "img"); m.src = it.full; if (it.kind === "video") m.controls = true; stage.replaceChildren(m); cap.textContent = [it.title, it.caption].filter(Boolean).join(" · "); view.hidden = false; }
view.querySelector(".close").onclick = () => { view.hidden = true; stage.replaceChildren(); };
view.querySelector(".prev").onclick = () => show(at - 1); view.querySelector(".next").onclick = () => show(at + 1);
document.addEventListener("keydown", (e) => { if (view.hidden) return; if (e.key === "Escape") view.querySelector(".close").onclick(); if (e.key === "ArrowLeft") show(at - 1); if (e.key === "ArrowRight") show(at + 1); });
</script></body></html>"""
