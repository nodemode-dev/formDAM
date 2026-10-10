import html
import json
import os
import tempfile
import threading
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from .db import ex, q1, reset_thread_conn
from .services import classify, sharesvc, thumbs

MAX_UPLOAD = 1024 * 1024 * 1024
COOKIE = "dam_share"
VIEW_ONLY_PX = 2048
FAIL_LIMIT = 8
FAIL_WINDOW_S = 600
_failures: Dict[str, List[float]] = {}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_server = None
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()


@app.middleware("http")
async def headers(request: Request, call_next):
    parts = request.url.path.strip("/").split("/")
    if request.method == "POST" and len(parts) == 3 and parts[0] == "s" and parts[2] == "contribute":
        try:
            size = int(request.headers.get("content-length") or "0")
        except ValueError:
            size = 0
        share = sharesvc.live(parts[1])
        reset_thread_conn()
        if share is None or not share["allow_contrib"] or share["kind"] != "album":
            return JSONResponse({"detail": "Adding photos is off for this album"}, status_code=403)
        if size <= 0 or size > MAX_UPLOAD + 65536:
            return JSONResponse({"detail": "That file is too large or the upload has no length"}, status_code=413)
        if sharesvc.needs_unlock(share, request.cookies.get(f"{COOKIE}_{parts[1]}")):
            return JSONResponse({"detail": "Password required"}, status_code=401)
    try:
        response = await call_next(request)
    finally:
        reset_thread_conn()
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


class UnlockIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class PostIn(BaseModel):
    kind: str = Field(pattern="^(comment|like)$")
    author: str = Field("", max_length=sharesvc.MAX_NAME)
    text: str = Field("", max_length=sharesvc.MAX_TEXT)
    media_id: Optional[int] = None


def _share(token: str, request: Request, open_only: bool = True):
    share = sharesvc.live(token)
    if share is None:
        raise HTTPException(404, detail="This link has expired or was turned off")
    if open_only and sharesvc.needs_unlock(share, request.cookies.get(f"{COOKIE}_{token}")):
        raise HTTPException(401, detail="Password required")
    return share


def _member(share, media_id: int):
    if not sharesvc.allowed(share, media_id):
        raise HTTPException(404, detail="Not in this share")
    return q1("SELECT * FROM media WHERE id=?", (media_id,))


@app.get("/s/{token}", response_class=HTMLResponse)
def page(token: str):
    share = sharesvc.live(token)
    if share is None:
        return HTMLResponse(_page("Link unavailable", "", {}), status_code=404)
    ex("UPDATE shares SET views=views+1 WHERE id=?", (share["id"],))
    flags = {"token": token, "download": bool(share["allow_download"]), "comments": bool(share["allow_comments"]),
             "contrib": bool(share["allow_contrib"]), "locked": bool(share["password_hash"]), "album": share["kind"] == "album",
             "owner": sharesvc.settings()["name"]}
    return HTMLResponse(_page(share["title"], token, flags))


@app.post("/s/{token}/unlock")
def unlock(token: str, body: UnlockIn, request: Request):
    share = _share(token, request, open_only=False)
    now = time.time()
    with _lock:
        recent = [t for t in _failures.get(token, []) if now - t < FAIL_WINDOW_S]
        _failures[token] = recent
    if len(recent) >= FAIL_LIMIT:
        raise HTTPException(429, detail="Too many tries. Wait a few minutes.")
    cookie = sharesvc.unlock(share, body.password)
    if cookie is None:
        with _lock:
            _failures.setdefault(token, []).append(now)
        raise HTTPException(403, detail="That password is not right")
    response = JSONResponse({"ok": True})
    response.set_cookie(f"{COOKIE}_{token}", cookie, max_age=sharesvc.COOKIE_TTL, httponly=True, samesite="strict", path=f"/s/{token}")
    return response


@app.get("/s/{token}/items")
def items(token: str, request: Request):
    share = _share(token, request)
    return {"title": share["title"], "items": sharesvc.items(share)}


@app.get("/s/{token}/t/{media_id}")
def thumb(token: str, media_id: int, request: Request, s: int = Query(384, ge=64, le=768)):
    share = _share(token, request)
    row = _member(share, media_id)
    path = thumbs.ensure_thumb(media_id, row["rel_path"], row["kind"], s)
    if not path or not os.path.isfile(path):
        raise HTTPException(404, detail="No thumbnail")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/s/{token}/r/{media_id}")
def still(token: str, media_id: int, request: Request, w: int = Query(2048, ge=256, le=4096)):
    share = _share(token, request)
    row = _member(share, media_id)
    if row["kind"] != "image":
        raise HTTPException(415, detail="Videos play from /v")
    path = sharesvc.still_path(media_id, w if share["allow_download"] else min(w, VIEW_ONLY_PX))
    if path is None:
        raise HTTPException(404, detail="This photo could not be shown")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/s/{token}/v/{media_id}")
def video(token: str, media_id: int, request: Request):
    share = _share(token, request)
    row = _member(share, media_id)
    if row["kind"] != "video":
        raise HTTPException(415, detail="Not a video")
    path = sharesvc.download_path(share, media_id)
    if path is None:
        raise HTTPException(404, detail="This video could not be shown")
    return FileResponse(path, media_type=row["mime"] or "video/mp4", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/s/{token}/d/{media_id}")
def download(token: str, media_id: int, request: Request):
    share = _share(token, request)
    if not share["allow_download"]:
        raise HTTPException(403, detail="Downloads are off for this link")
    row = _member(share, media_id)
    path = sharesvc.download_path(share, media_id)
    if path is None:
        raise HTTPException(404, detail="This file could not be prepared")
    stem = os.path.splitext(row["name"])[0]
    return FileResponse(path, filename=stem + os.path.splitext(path)[1])


@app.get("/s/{token}/activity")
def activity(token: str, request: Request, media_id: Optional[int] = None):
    share = _share(token, request)
    if media_id is not None:
        _member(share, media_id)
    rows = sharesvc.activity(share["id"], media_id)
    return {"activity": [{k: r[k] for k in ("id", "media_id", "kind", "author", "text", "ts", "owner")} for r in rows]}


@app.post("/s/{token}/post")
def post(token: str, body: PostIn, request: Request):
    share = _share(token, request)
    if not share["allow_comments"]:
        raise HTTPException(403, detail="Comments are off for this link")
    if body.media_id is not None:
        _member(share, body.media_id)
    try:
        return sharesvc.post(share, body.kind, body.author, body.text, body.media_id)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))


@app.post("/s/{token}/contribute")
def contribute(token: str, request: Request, file: UploadFile = File(...), author: str = Form("")):
    share = _share(token, request)
    if not share["allow_contrib"] or share["kind"] != "album":
        raise HTTPException(403, detail="Adding photos is off for this album")
    name = os.path.basename(file.filename or "upload")
    kind, _ = classify.media_kind(name)
    if not kind:
        raise HTTPException(415, detail="Only photos and videos can be added")
    folder = tempfile.mkdtemp(prefix="dam-contrib-")
    path = os.path.join(folder, name)
    size = 0
    with open(path, "wb") as handle:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD:
                handle.close()
                os.unlink(path)
                raise HTTPException(413, detail="That file is too large")
            handle.write(chunk)
    try:
        result = sharesvc.contribute(share, path, author)
    finally:
        try:
            if os.path.isfile(path):
                os.unlink(path)
            os.rmdir(folder)
        except OSError:
            pass
    if result.get("status") == "imported":
        from .services import followon

        followon.start_after_import({"imported": 1})
    return {"status": result.get("status")}


@app.get("/{rest:path}")
def nothing(rest: str):
    return Response(status_code=404)


def running() -> bool:
    return _thread is not None and _thread.is_alive()


def start() -> bool:
    global _server, _thread
    import uvicorn

    with _lock:
        if running():
            return True
        conf = sharesvc.settings()
        config = uvicorn.Config(app, host="0.0.0.0", port=conf["port"], log_level="warning", access_log=False)
        _server = uvicorn.Server(config)
        _server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        _thread = threading.Thread(target=_server.run, name="DAM-share", daemon=True)
        _thread.start()
    for _ in range(40):
        if _server.started:
            return True
        if not _thread.is_alive():
            return False
        threading.Event().wait(0.05)
    return _server.started


def stop() -> None:
    global _server, _thread
    with _lock:
        if _server is not None:
            _server.should_exit = True
        if _thread is not None:
            _thread.join(timeout=5)
        _server, _thread = None, None


def sync_state() -> bool:
    if sharesvc.settings()["enabled"]:
        return start()
    stop()
    return False


def _page(title: str, token: str, flags: dict) -> str:
    safe_title = html.escape(title)
    data = html.escape(json.dumps(flags), quote=True)
    return PAGE.replace("{{title}}", safe_title).replace("{{flags}}", data)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{title}}</title>
<style>
:root { --bg: #0d0d0f; --panel: #17171a; --line: #2a2a2f; --text: #f2f2f4; --muted: #a0a0a8; --accent: #f5a524; --danger: #ff5a52; --layer-viewer: 10; --layer-toast: 20; color-scheme: dark; }
@media (prefers-color-scheme: light) { :root { --bg: #f6f6f7; --panel: #ffffff; --line: #dedee2; --text: #18181b; --muted: #5d5d66; color-scheme: light; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { display: flex; align-items: baseline; gap: 12px; padding: 20px 16px 8px; flex-wrap: wrap; }
h1 { font-size: 22px; margin: 0; }
.sub { color: var(--muted); font-size: 13px; }
main { padding: 8px 16px 40px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 4px; }
.cell { position: relative; aspect-ratio: 1; background: var(--panel); border: 0; padding: 0; cursor: pointer; overflow: hidden; border-radius: 4px; }
.cell img { width: 100%; height: 100%; object-fit: cover; display: block; }
.badge { position: absolute; left: 6px; bottom: 6px; font-size: 11px; padding: 1px 6px; border-radius: 8px; background: rgba(0,0,0,.6); color: #fff; }
.bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0 16px; }
button.btn, label.btn, a.btn { text-decoration: none; display: inline-block; font: inherit; font-size: 13px; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--panel); color: var(--text); cursor: pointer; }
button.btn.on { border-color: var(--accent); color: var(--accent); }
input[type=text], input[type=password], textarea { font: inherit; width: 100%; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); background: var(--panel); color: var(--text); }
.viewer { position: fixed; inset: 0; z-index: var(--layer-viewer); background: rgba(0,0,0,.94); display: grid; grid-template-columns: 1fr minmax(0, 320px); }
.viewer[hidden] { display: none; }
.stage { position: relative; display: flex; align-items: center; justify-content: center; min-height: 0; }
.stage img, .stage video { max-width: 100%; max-height: 100vh; object-fit: contain; }
.side { background: var(--panel); color: var(--text); padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.close { position: absolute; top: 12px; right: 12px; }
.nav { position: absolute; top: 50%; transform: translateY(-50%); }
.nav.prev { left: 12px; } .nav.next { right: 12px; }
.act { font-size: 13px; border-bottom: 1px solid var(--line); padding: 6px 0; }
.act b { font-weight: 600; }
.feed { margin-top: 24px; max-width: 640px; }
.lock { max-width: 360px; margin: 15vh auto; display: flex; flex-direction: column; gap: 10px; padding: 0 16px; }
.toast { position: fixed; left: 50%; bottom: 20px; transform: translateX(-50%); z-index: var(--layer-toast); background: var(--panel); border: 1px solid var(--line); padding: 8px 14px; border-radius: 10px; }
.toast[hidden] { display: none; }
@media (max-width: 720px) { .viewer { grid-template-columns: 1fr; grid-template-rows: 1fr auto; } .side { max-height: 40vh; } }
</style></head>
<body>
<div id="app" data-flags="{{flags}}"></div>
<div class="toast" id="toast" hidden></div>
<script>
(() => {
const F = JSON.parse(document.getElementById("app").dataset.flags || "{}");
const app = document.getElementById("app");
const base = "/s/" + F.token;
const el = (tag, attrs, ...kids) => { const n = document.createElement(tag); for (const [k, v] of Object.entries(attrs || {})) { if (k === "text") n.textContent = v; else n.setAttribute(k, v); } n.append(...kids.filter(Boolean)); return n; };
let me = ""; try { me = localStorage.getItem("dam-guest-name") || ""; } catch (e) { me = ""; }
const toastEl = document.getElementById("toast");
const toast = (msg) => { toastEl.textContent = msg; toastEl.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => { toastEl.hidden = true; }, 2600); };
const api = async (path, init) => { const r = await fetch(base + path, Object.assign({ credentials: "same-origin", headers: { "Content-Type": "application/json" } }, init || {})); if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail || d; } catch (e) {} const err = new Error(d); err.status = r.status; throw err; } return r.json(); };
const askName = () => { if (me) return me; const v = (prompt("Your name, shown with what you post") || "").trim().slice(0, 60); if (v) { me = v; try { localStorage.setItem("dam-guest-name", v); } catch (e) {} } return me; };
if (!F.token) { app.append(el("div", { class: "lock" }, el("h1", { text: "This link is unavailable" }), el("p", { class: "sub", text: "It may have expired or been turned off by the owner." }))); return; }
let items = [];
let index = -1;
async function boot() {
  try { items = (await api("/items")).items; } catch (e) { if (e.status === 401) return lockScreen(); app.append(el("p", { text: e.message })); return; }
  render();
}
function lockScreen() {
  const pw = el("input", { type: "password", placeholder: "Password", autocomplete: "current-password" });
  const go = el("button", { class: "btn", type: "button", text: "View" });
  const msg = el("p", { class: "sub" });
  const tryIt = async () => { try { await api("/unlock", { method: "POST", body: JSON.stringify({ password: pw.value }) }); wrap.remove(); boot(); } catch (e) { msg.textContent = e.message; } };
  go.addEventListener("click", tryIt); pw.addEventListener("keydown", (e) => { if (e.key === "Enter") tryIt(); });
  const wrap = el("div", { class: "lock" }, el("h1", { text: document.title }), el("p", { class: "sub", text: "Shared by " + F.owner + ". Enter the password you were given." }), pw, go, msg);
  app.append(wrap); pw.focus();
}
function render() {
  const head = el("header", {}, el("h1", { text: document.title }), el("span", { class: "sub", text: (F.album ? "Shared album from " : "Shared by ") + F.owner + " · " + items.length + " item" + (items.length === 1 ? "" : "s") }));
  const bar = el("div", { class: "bar" });
  if (F.contrib) {
    const input = el("input", { type: "file", accept: "image/*,video/*", multiple: "", hidden: "" });
    const label = el("label", { class: "btn", text: "Add Photos" }); label.append(input);
    input.addEventListener("change", async () => {
      const who = askName(); let added = 0;
      for (const f of input.files) { const fd = new FormData(); fd.append("file", f); fd.append("author", who); const r = await fetch(base + "/contribute", { method: "POST", body: fd, credentials: "same-origin" }); if (r.ok) added++; }
      toast(added + " added"); input.value = ""; items = (await api("/items")).items; paintGrid();
    });
    bar.append(label);
  }
  const grid = el("div", { class: "grid" });
  const feed = el("div", { class: "feed" });
  app.append(head, el("main", {}, bar, grid, feed));
  render.grid = grid; render.feed = feed;
  paintGrid(); paintFeed();
}
function paintGrid() {
  const grid = render.grid; const keep = new Map([...grid.children].map((n) => [n.dataset.id, n]));
  const next = items.map((it, i) => {
    let cell = keep.get(String(it.id));
    if (!cell) { cell = el("button", { class: "cell", type: "button", "data-id": String(it.id), "aria-label": "Open item " + (i + 1) }, el("img", { src: base + "/t/" + it.id + "?s=384", alt: it.title || "", loading: "lazy" })); }
    cell.onclick = () => openAt(items.findIndex((x) => x.id === it.id));
    let badge = cell.querySelector(".badge"); const label = it.kind === "video" ? "Video" : (it.likes ? it.likes + " like" + (it.likes === 1 ? "" : "s") : "");
    if (label && !badge) { badge = el("span", { class: "badge" }); cell.append(badge); }
    if (badge) { if (label) badge.textContent = label; else badge.remove(); }
    return cell;
  });
  grid.replaceChildren(...next);
}
async function paintFeed() {
  if (!F.comments && !F.contrib) return;
  const rows = (await api("/activity")).activity.slice(0, 30);
  render.feed.replaceChildren(el("h2", { class: "sub", text: "Activity" }), ...rows.map(actRow));
}
function actRow(a) {
  const what = a.kind === "like" ? " liked a photo" : a.kind === "contrib" ? " added a photo" : ": ";
  return el("div", { class: "act" }, el("b", { text: a.author + (a.owner ? " (owner)" : "") }), document.createTextNode(what), a.kind === "comment" ? document.createTextNode(a.text) : null);
}
const viewer = el("div", { class: "viewer", hidden: "" });
const stage = el("div", { class: "stage" });
const side = el("div", { class: "side" });
const close = el("button", { class: "btn close", type: "button", text: "Close" });
const prev = el("button", { class: "btn nav prev", type: "button", text: "Previous" });
const next = el("button", { class: "btn nav next", type: "button", text: "Next" });
stage.append(close, prev, next); viewer.append(stage, side); document.body.append(viewer);
close.onclick = () => { viewer.hidden = true; index = -1; stage.querySelector("img, video")?.remove(); };
prev.onclick = () => openAt(Math.max(0, index - 1)); next.onclick = () => openAt(Math.min(items.length - 1, index + 1));
document.addEventListener("keydown", (e) => { if (viewer.hidden) return; if (e.key === "Escape") close.onclick(); if (e.key === "ArrowLeft") prev.onclick(); if (e.key === "ArrowRight") next.onclick(); });
async function openAt(i) {
  if (i < 0 || i >= items.length) return;
  index = i; const it = items[i]; viewer.hidden = false;
  const media = it.kind === "video" ? el("video", { src: base + "/v/" + it.id, controls: "", playsinline: "" }) : el("img", { src: base + "/r/" + it.id + "?w=2048", alt: it.title || "" });
  const old = stage.querySelector("img, video");
  if (it.kind === "video" || !old) { if (old) old.replaceWith(media); else stage.prepend(media); }
  else { media.decode().then(() => { if (index === i) old.replaceWith(media); }).catch(() => { if (index === i) old.replaceWith(media); }); }
  prev.disabled = i === 0; next.disabled = i === items.length - 1;
  const kids = [];
  if (it.title) kids.push(el("h2", { text: it.title }));
  if (it.caption) kids.push(el("p", { text: it.caption }));
  const row = el("div", { class: "bar" });
  if (F.comments) { const like = el("button", { class: "btn", type: "button", text: "Like" + (it.likes ? " (" + it.likes + ")" : "") }); like.onclick = async () => { if (!askName()) return; const r = await api("/post", { method: "POST", body: JSON.stringify({ kind: "like", author: me, media_id: it.id }) }); it.likes += r.liked === false ? -1 : 1; like.textContent = "Like" + (it.likes ? " (" + it.likes + ")" : ""); like.classList.toggle("on", r.liked !== false); paintGrid(); }; row.append(like); }
  if (F.download) row.append(el("a", { class: "btn", href: base + "/d/" + it.id, download: "", text: "Download" }));
  kids.push(row);
  if (F.comments) {
    const list = el("div", {});
    const box = el("textarea", { rows: "2", placeholder: "Add a comment" });
    const send = el("button", { class: "btn", type: "button", text: "Post" });
    send.onclick = async () => { if (!box.value.trim() || !askName()) return; try { const a = await api("/post", { method: "POST", body: JSON.stringify({ kind: "comment", author: me, text: box.value, media_id: it.id }) }); list.append(actRow(a)); box.value = ""; paintFeed(); } catch (e) { toast(e.message); } };
    kids.push(list, box, send);
    api("/activity?media_id=" + it.id).then((r) => { if (index === i) list.replaceChildren(...r.activity.filter((a) => a.kind === "comment").map(actRow)); });
  }
  side.replaceChildren(...kids);
}
boot();
})();
</script></body></html>"""
