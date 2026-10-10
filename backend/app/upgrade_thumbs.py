"""Standalone thumbnail upgrader: legacy JPEG thumbs -> WebP v4.

Same pixel resolution, materially smaller files, so the grid has less to load.
Idempotent & resumable: already-converted files are skipped, & a marker file
(.v4_done) records completion so later launches cost one stat call.

Invocations:
- Automatically at first launch: the engine spawns run_async() from lifespan
  when the marker is absent (background thread, niced, starts after a short
  delay so boot is never contended).
- Manually: python3 -m app.upgrade_thumbs   (from backend/)
  or: python3 app/upgrade_thumbs.py
"""

import os
import sys
import threading
import time


def _cache_dir() -> str:
    try:
        from .config import cache_dir
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app.config import cache_dir
    return cache_dir()


def main() -> int:
    try:
        os.nice(10)
    except (OSError, AttributeError):
        pass
    folder = os.path.join(_cache_dir(), "thumbs")
    marker = os.path.join(folder, ".v4_done")
    if os.path.isfile(marker):
        return 0
    os.makedirs(folder, exist_ok=True)
    from PIL import Image

    converted = 0
    removed = 0
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if name.endswith("_v3.jpg"):
            dst = os.path.join(folder, name[: -len("_v3.jpg")] + "_v4.webp")
            if os.path.isfile(dst):
                try:
                    os.unlink(path)
                    removed += 1
                except OSError:
                    pass
                continue
            tmp = dst + ".tmp"
            try:
                with Image.open(path) as img:
                    img.convert("RGB").save(tmp, "WEBP", quality=80, method=4)
                os.replace(tmp, dst)
                os.unlink(path)
                converted += 1
            except Exception:
                if os.path.isfile(tmp):
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
        elif name.endswith("_ph.jpg") or "_v1.jpg" in name or "_v2.jpg" in name:
            # Placeholders & pre-v3 leftovers regenerate on demand as WebP.
            try:
                os.unlink(path)
                removed += 1
            except OSError:
                pass
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write(str(int(time.time())))
    print(f"thumb upgrade: {converted} converted, {removed} removed", flush=True)
    return 0


def run_async(delay_seconds: float = 3.0) -> None:
    """First-launch trigger: convert in the background w/o contending boot."""
    folder = os.path.join(_cache_dir(), "thumbs")
    if os.path.isfile(os.path.join(folder, ".v4_done")):
        return

    def worker() -> None:
        time.sleep(delay_seconds)
        try:
            main()
        except Exception:
            pass

    threading.Thread(target=worker, name="thumb-upgrade", daemon=True).start()


if __name__ == "__main__":
    raise SystemExit(main())
