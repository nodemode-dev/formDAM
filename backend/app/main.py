import mimetypes
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import VERSION, cache_dir, env, originals_dir
from . import ffmpeg_fetch, mediacodecs, upgrade_thumbs, wiring
from .db import init_db, q, ex, setting_get, setting_set
from .services import classify
from .routers import albums, automation, browse, curate, dedup, discover, edit, files, geo, importer, library, mediaapi, organize, output, packages, people, render, syncapi, system, trash
from .security import local_only_guard

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
ffmpeg_fetch.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from . import security
    if security.LAUNCH_GENERATED:
        print("formDAM: no launcher key was given; open the interface with this address (it connects the window):\n"
              f"formDAM:   http://127.0.0.1:8000/#dam-key={security.LAUNCH_KEY}  (use the port the engine or the dev server runs on)",
              file=sys.stderr, flush=True)
    os.makedirs(originals_dir(), exist_ok=True)
    os.makedirs(cache_dir(), exist_ok=True)
    from . import vaultcrypt
    vaultcrypt.startup()
    trash.purge_expired()
    from .services import housekeeping
    housekeeping.register(trash.purge_expired)
    housekeeping.register(browse.ensure_backfill)
    housekeeping.register(geo.ensure_geo_backfill)
    housekeeping.register(discover.ensure_clip)
    housekeeping.register(discover.ensure_lookup)
    housekeeping.register(output.ensure_sidecars)
    housekeeping.register(curate.ensure_memories)
    output.start_autosave()
    housekeeping.start()
    browse.ensure_backfill()
    geo.ensure_geo_backfill()
    discover.ensure_clip()
    discover.ensure_lookup()
    curate.ensure_memories()
    _reclassify_screenshots()
    upgrade_thumbs.run_async()
    from . import familyserver
    from .services import syncsvc
    try:
        familyserver.sync_state()
    except Exception:
        pass
    housekeeping.register(syncsvc.ensure)
    syncsvc.ensure()
    yield
    familyserver.stop()


def _reclassify_screenshots() -> None:
    if setting_get("classify_ver") == "2":
        return
    for row in q("SELECT id, name, mime, created_src, width, height, is_screenshot FROM media"):
        flag = 1 if classify.looks_screenshot(
            row["name"], row["mime"], row["created_src"] == "exif", row["width"], row["height"]
        ) else 0
        if flag != row["is_screenshot"]:
            ex("UPDATE media SET is_screenshot=? WHERE id=?", (flag, row["id"]))
    setting_set("classify_ver", "2")


mediacodecs.register()
wiring.connect()
app = FastAPI(title="formDAM", version=VERSION, lifespan=lifespan)
app.middleware("http")(local_only_guard)

for module in (automation, system, importer, browse, render, edit, organize, files, geo, discover, output, curate, library, packages, syncapi, mediaapi, albums, people, trash, dedup):
    app.include_router(module.router, prefix="/api")

_dist = env("DIST", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist"))
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
