import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import VERSION, cache_dir, originals_dir
from . import mediacodecs, upgrade_thumbs, wiring
from .db import init_db, q, ex, setting_get, setting_set
from .services import classify
from .routers import albums, browse, dedup, discover, edit, files, geo, importer, mediaapi, organize, output, people, render, system, trash
from .security import local_only_guard


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
    housekeeping.register(output.ensure_sidecars)
    output.start_autosave()
    housekeeping.start()
    browse.ensure_backfill()
    geo.ensure_geo_backfill()
    discover.ensure_clip()
    _reclassify_screenshots()
    upgrade_thumbs.run_async()
    yield


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
app = FastAPI(title="DAM", version=VERSION, lifespan=lifespan)
app.middleware("http")(local_only_guard)

for module in (system, importer, browse, render, edit, organize, files, geo, discover, output, mediaapi, albums, people, trash, dedup):
    app.include_router(module.router, prefix="/api")

_dist = os.environ.get(
    "DAM_DIST",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist"),
)
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
