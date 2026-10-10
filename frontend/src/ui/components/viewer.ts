import { api, fileUrl, stillUrl, thumbUrl } from "../../engine/api.js";
import { countFmt, timeLabel, dayLabel } from "../../engine/format.js";
import { closeViewer, dropFromCaches, markViewed, on, patched, saveMeta, setFavorite, state, stepViewer, trashMedia } from "../../engine/store.js";
import { createInfoPanel, type InfoPanel } from "./infopanel.js";
import { h } from "../dom.js";
import { iconEl, iconInto } from "../icons.js";
import { toast } from "../toast.js";

let filmIds: number[] | null = null;
let filmTrack: HTMLElement | null = null;
let filmWrap: HTMLElement | null = null;
let filmFresh = false;
let filmHideTimer: number | undefined;
let filmHovered = false;

function showFilmstrip(temporary: boolean): void {
  if (!filmWrap) return;
  filmWrap.classList.add("visible");
  window.clearTimeout(filmHideTimer);
  if (temporary) {
    filmHideTimer = window.setTimeout(() => {
      if (!filmHovered) filmWrap?.classList.remove("visible");
    }, 1300);
  }
}
let filmStep: (idx: number) => void = () => undefined;

export const viewerHooks: {
  editLocation?: (id: number) => void;
  editDate?: (id: number) => void;
  onShow?: (id: number) => void;
  refreshInfo?: () => void;
  toolbar: Array<(id: () => number | null) => HTMLElement>;
  keys: Array<(event: KeyboardEvent, id: number) => boolean>;
} = { toolbar: [], keys: [] };

const LABEL_KEYS: Record<string, string> = { "6": "red", "7": "yellow", "8": "green", "9": "blue" };

export function ratingKey(event: KeyboardEvent, ids: number[]): boolean {
  if (event.metaKey || event.ctrlKey || event.altKey || ids.length === 0) return false;
  const target = event.target as HTMLElement | null;
  if (target && target.closest("input, textarea, select, [contenteditable=\"true\"]")) return false;
  if (/^[0-5]$/.test(event.key)) {
    void saveMeta(ids, { rating: Number(event.key) });
    return true;
  }
  if (event.key in LABEL_KEYS) {
    const first = state.byId.get(ids[0]);
    const label = LABEL_KEYS[event.key];
    void saveMeta(ids, { label: first?.label === label ? "" : label });
    return true;
  }
  if (event.key === "x" || event.key === "X") {
    const first = state.byId.get(ids[0]);
    void saveMeta(ids, { rejected: !first?.rejected });
    return true;
  }
  if (event.key === ".") {
    const first = state.byId.get(ids[0]);
    void saveMeta(ids, { favorite: !first?.favorite });
    return true;
  }
  return false;
}

const FILM_STRIDE = 58;
const FILM_PAD = 44;
const FILM_WINDOW = 24;

function filmMaterialize(ids: number[], from: number, to: number): void {
  if (!filmTrack) return;
  const lo = Math.max(0, from);
  const hi = Math.min(ids.length - 1, to);
  for (let idx = lo; idx <= hi; idx++) {
    const btn = filmTrack.children[idx] as HTMLElement | undefined;
    if (!btn || btn.dataset.loaded === "1") continue;
    btn.dataset.loaded = "1";
    btn.append(h("img", { alt: "", src: thumbUrl(ids[idx], 192), draggable: "false" }));
  }
}

function buildFilmstrip(ids: number[]): void {
  const track = h("div", { class: "film-track" });
  for (let idx = 0; idx < ids.length; idx++) {
    const btn = h("button", { class: "film-thumb", type: "button", "data-idx": String(idx) });
    btn.addEventListener("click", () => filmStep(idx));
    track.append(btn);
  }
  let scrollQueued = false;
  track.addEventListener("scroll", () => {
    if (scrollQueued) return;
    scrollQueued = true;
    requestAnimationFrame(() => {
      scrollQueued = false;
      const first = Math.floor((track.scrollLeft - FILM_PAD) / FILM_STRIDE);
      const count = Math.ceil(track.clientWidth / FILM_STRIDE);
      filmMaterialize(ids, first - 10, first + count + 10);
    });
  }, { passive: true });
  let wheelBudget = 0;
  let wheelLatched = false;
  let wheelQuiet: number | undefined;
  track.addEventListener("wheel", (event) => {
    event.preventDefault();
    window.clearTimeout(wheelQuiet);
    wheelQuiet = window.setTimeout(() => {
      wheelLatched = false;
      wheelBudget = 0;
    }, 160);
    if (wheelLatched) return;
    const delta = Math.abs(event.deltaY) > Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
    wheelBudget += delta;
    if (Math.abs(wheelBudget) < 42) return;
    const direction = wheelBudget > 0 ? 1 : -1;
    wheelBudget = 0;
    wheelLatched = true;
    if (!state.viewer) return;
    const next = Math.min(ids.length - 1, Math.max(0, state.viewer.index + direction));
    if (next !== state.viewer.index) filmStep(next);
  }, { passive: false });
  let dragging = false;
  let dragStartX = 0;
  let dragStartScroll = 0;
  track.addEventListener("pointerdown", (event) => {
    dragging = true;
    dragStartX = event.clientX;
    dragStartScroll = track.scrollLeft;
    track.setPointerCapture(event.pointerId);
    track.classList.add("panning");
  });
  track.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    track.scrollLeft = dragStartScroll - (event.clientX - dragStartX);
  });
  const stopDrag = () => {
    dragging = false;
    track.classList.remove("panning");
  };
  track.addEventListener("pointerup", stopDrag);
  track.addEventListener("pointercancel", stopDrag);
  filmTrack = track;
  filmFresh = true;
  filmWrap = h("div", { class: "film-strip-wrap" },
    h("div", { class: "film-strip pop-surface" },
      h("div", { class: "film-cap left" }), track, h("div", { class: "film-cap right" })));
  filmWrap.addEventListener("pointerenter", () => {
    filmHovered = true;
    showFilmstrip(false);
  });
  filmWrap.addEventListener("pointerleave", () => {
    filmHovered = false;
    showFilmstrip(true);
  });
}

function syncFilmstrip(index: number): void {
  if (!filmTrack || !filmIds) return;
  showFilmstrip(true);
  for (const el of filmTrack.querySelectorAll(".film-thumb.current")) el.classList.remove("current");
  const current = filmTrack.children[index] as HTMLElement | undefined;
  if (!current) return;
  current.classList.add("current");
  filmMaterialize(filmIds, index - FILM_WINDOW, index + FILM_WINDOW);
  const target = FILM_PAD + index * FILM_STRIDE + 26 - filmTrack.clientWidth / 2;
  filmTrack.scrollTo({ left: Math.max(0, target), behavior: filmFresh ? "auto" : "smooth" });
  filmFresh = false;
}


export function mountViewer(host: HTMLElement): void {
  let root: HTMLElement | null = null;
  let infoOpen = false;

  let vDate: HTMLElement;
  let vPos: HTMLElement;
  let favBtn: HTMLButtonElement;
  let downloadLink: HTMLAnchorElement;
  let prevBtn: HTMLButtonElement;
  let nextBtn: HTMLButtonElement;
  let imgA: HTMLImageElement;
  let imgB: HTMLImageElement;
  let videoHolder: HTMLElement;
  let liveHolder: HTMLElement;
  let liveBtn: HTMLButtonElement;
  let stripSlot: HTMLElement;
  let infoPanel: HTMLElement;
  let info: InfoPanel;
  let frontIsA = true;
  let mediaSeq = 0;
  let zoomLayer: HTMLElement;
  let zoomBox: HTMLElement;
  let resetBtn: HTMLButtonElement;
  let zScale = 1;
  let zTx = 0;
  let zTy = 0;

  function applyZoom(animated = true): void {
    zoomLayer.style.transition = animated ? "transform 200ms var(--ease)" : "none";
    zoomLayer.style.transform = `translate(${zTx}px, ${zTy}px) scale(${zScale})`;
    resetBtn.disabled = zScale === 1;
  }

  function resetZoom(animated = true): void {
    zScale = 1;
    zTx = 0;
    zTy = 0;
    applyZoom(animated);
  }

  function currentId(): number | null {
    if (!state.viewer) return null;
    return state.viewer.ids[state.viewer.index] ?? null;
  }

  function dropCurrentAndContinue(id: number): void {
    const ids = state.viewer!.ids.filter((x) => x !== id);
    if (ids.length === 0) closeViewer();
    else {
      state.viewer = { ids, index: Math.min(state.viewer!.index, ids.length - 1) };
      update();
    }
  }

  let savedScroll: { el: HTMLElement; top: number } | null = null;

  function build(): void {
    const scroller = document.querySelector<HTMLElement>(".content > .view");
    savedScroll = scroller ? { el: scroller, top: scroller.scrollTop } : null;
    imgA = h("img", { class: "stage-img", alt: "" }) as HTMLImageElement;
    imgB = h("img", { class: "stage-img", alt: "" }) as HTMLImageElement;
    videoHolder = h("div", { class: "stage-video hidden" });
    liveHolder = h("div", { class: "stage-video stage-live hidden" });
    zoomLayer = h("div", { class: "zoom-layer" }, imgA, imgB, videoHolder, liveHolder);
    zoomBox = h("div", { class: "zoom-box hidden" });
    const media = h("div", { class: "stage-media" }, zoomLayer, zoomBox);
    const stage = h("div", { class: "viewer-stage" }, media);
    media.addEventListener("dblclick", () => resetZoom());
    media.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const item = state.byId.get(currentId() ?? -1);
      if (!item || item.kind === "video") return;
      if (zScale === 1 && !(event.target as HTMLElement).classList.contains("stage-img")) return;
      const rect = media.getBoundingClientRect();
      const startX = event.clientX;
      const startY = event.clientY;
      if (zScale > 1) {
        const panStartTx = zTx;
        const panStartTy = zTy;
        let panning = false;
        zoomLayer.classList.add("panning");
        const move = (ev: PointerEvent) => {
          if (!panning && Math.hypot(ev.clientX - startX, ev.clientY - startY) < 4) return;
          panning = true;
          zTx = panStartTx + (ev.clientX - startX);
          zTy = panStartTy + (ev.clientY - startY);
          applyZoom(false);
        };
        const up = () => {
          zoomLayer.classList.remove("panning");
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
        return;
      }
      let boxing = false;
      const move = (ev: PointerEvent) => {
        if (!boxing && Math.hypot(ev.clientX - startX, ev.clientY - startY) < 6) return;
        boxing = true;
        zoomBox.classList.remove("hidden");
        const x = Math.min(startX, ev.clientX) - rect.left;
        const y = Math.min(startY, ev.clientY) - rect.top;
        const w = Math.abs(ev.clientX - startX);
        const hgt = Math.abs(ev.clientY - startY);
        zoomBox.style.left = `${x}px`;
        zoomBox.style.top = `${y}px`;
        zoomBox.style.width = `${w}px`;
        zoomBox.style.height = `${hgt}px`;
      };
      const up = (ev: PointerEvent) => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        zoomBox.classList.add("hidden");
        if (!boxing) return;
        const w = Math.abs(ev.clientX - startX);
        const hgt = Math.abs(ev.clientY - startY);
        if (w < 24 || hgt < 24) return;
        const factor = Math.min(rect.width / w, rect.height / hgt, 8);
        const centerX = (Math.min(startX, ev.clientX) + w / 2) - (rect.left + rect.width / 2);
        const centerY = (Math.min(startY, ev.clientY) + hgt / 2) - (rect.top + rect.height / 2);
        const vx = (centerX - zTx) / zScale;
        const vy = (centerY - zTy) / zScale;
        zScale = Math.min(8, zScale * factor);
        zTx = -zScale * vx;
        zTy = -zScale * vy;
        applyZoom();
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
    stage.addEventListener("wheel", (event) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      if (event.deltaY > 14) {
        if (zScale > 1) resetZoom();
        else closeViewer();
      }
    }, { passive: false });
    stage.addEventListener("click", (event) => {
      if (event.target === stage || event.target === media) closeViewer();
    });

    prevBtn = h("button", { class: "viewer-arrow prev", type: "button", "aria-label": "Previous" }, iconEl("arrowLeft")) as HTMLButtonElement;
    nextBtn = h("button", { class: "viewer-arrow next", type: "button", "aria-label": "Next" }, iconEl("chevron")) as HTMLButtonElement;
    prevBtn.addEventListener("click", () => stepViewer(-1));
    nextBtn.addEventListener("click", () => stepViewer(1));
    liveBtn = h("button", { class: "live-btn hidden", type: "button", title: "Play Live Photo" }, iconEl("play"), "LIVE") as HTMLButtonElement;
    liveBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      const item = state.byId.get(currentId() ?? -1);
      if (!item || !item.live_video_id) return;
      if (liveHolder.classList.contains("hidden")) playLive(item.live_video_id);
      else stopLive();
    });
    stage.append(prevBtn, nextBtn, liveBtn);

    favBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Favorite" }) as HTMLButtonElement;
    favBtn.addEventListener("click", async () => {
      const id = currentId();
      if (id === null) return;
      await setFavorite(id, !state.byId.get(id)!.favorite);
      patchFav(id);
    });

    const infoBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Info" }, iconEl("info"));
    infoBtn.addEventListener("click", () => {
      infoOpen = !infoOpen;
      infoBtn.classList.toggle("active", infoOpen);
      infoPanel.classList.toggle("hidden", !infoOpen);
      const id = currentId();
      if (infoOpen && id !== null) info.show(id);
    });

    downloadLink = h("a", { class: "icon-btn", href: "#", "aria-label": "Download" }, iconEl("download")) as HTMLAnchorElement;
    resetBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Reset view" }, iconEl("reset")) as HTMLButtonElement;
    resetBtn.disabled = true;
    resetBtn.addEventListener("click", () => resetZoom());

    const hideBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Hide" }, iconEl("eyeOff"));
    hideBtn.addEventListener("click", async () => {
      const id = currentId();
      if (id === null) return;
      await api(`/media/${id}/hide`, { method: "POST" });
      dropFromCaches(id);
      toast("Hidden. Find it under Utilities, behind the vault passkey.");
      dropCurrentAndContinue(id);
    });
    const trashBtn = h("button", { class: "icon-btn danger", type: "button", "aria-label": "Move to Recently Deleted" }, iconEl("trash"));
    trashBtn.addEventListener("click", async () => {
      const id = currentId();
      if (id === null) return;
      await trashMedia(id);
      toast("Moved to Recently Deleted");
      dropCurrentAndContinue(id);
    });
    const closeBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Close" }, iconEl("close"));
    closeBtn.addEventListener("click", closeViewer);

    vDate = h("div", { class: "v-date" }, "");
    vPos = h("div", { class: "v-pos" }, "");
    info = createInfoPanel((id) => viewerHooks.editLocation?.(id), (id) => viewerHooks.editDate?.(id));
    const panel = info;
    viewerHooks.refreshInfo = () => panel.refresh();
    infoPanel = info.el;
    infoPanel.classList.toggle("hidden", !infoOpen);
    stripSlot = h("div", { class: "strip-slot" });

    const top = h("div", { class: "viewer-top" },
      closeBtn,
      h("div", { class: "viewer-title" }, vDate, vPos),
      infoBtn, resetBtn, downloadLink, favBtn, hideBtn, trashBtn);
    const main = h("div", { class: "viewer-main" }, stage, stripSlot, infoPanel);
    root = h("div", { class: "viewer" }, top, main);
    host.append(root);
    requestAnimationFrame(() => root && root.classList.add("open"));
  }

  function patchFav(id: number): void {
    const now = state.byId.get(id);
    if (!now) return;
    iconInto(favBtn, now.favorite ? "heartFill" : "heart");
    favBtn.classList.toggle("active", now.favorite);
  }

  function stopLive(): void {
    liveHolder.classList.add("hidden");
    liveHolder.replaceChildren();
    liveBtn.classList.remove("playing");
  }

  function playLive(videoId: number): void {
    const video = h("video", { src: fileUrl(videoId), autoplay: true, playsinline: true }) as HTMLVideoElement;
    video.addEventListener("ended", stopLive, { once: true });
    video.addEventListener("error", stopLive, { once: true });
    video.addEventListener("click", stopLive, { once: true });
    liveHolder.replaceChildren(video);
    liveHolder.classList.remove("hidden");
    liveBtn.classList.add("playing");
  }

  function showImage(id: number, name: string): void {
    const seq = ++mediaSeq;
    videoHolder.classList.add("hidden");
    videoHolder.replaceChildren();
    stopLive();
    const back = frontIsA ? imgB : imgA;
    const front = frontIsA ? imgA : imgB;
    back.alt = name;
    const reveal = () => {
      if (seq !== mediaSeq) return;
      back.classList.add("active");
      front.classList.remove("active");
      frontIsA = !frontIsA;
      const full = new Image();
      const known = state.byId.get(id);
      full.src = known ? stillUrl(known) : fileUrl(id);
      full.addEventListener("load", () => {
        if (seq === mediaSeq) back.src = full.src;
      }, { once: true });
    };
    back.addEventListener("load", reveal, { once: true });
    back.src = thumbUrl(id, 768);
    if (back.complete && back.naturalWidth > 0) reveal();
  }

  function showVideo(id: number): void {
    mediaSeq++;
    imgA.classList.remove("active");
    imgB.classList.remove("active");
    stopLive();
    videoHolder.classList.remove("hidden");
    videoHolder.replaceChildren(h("video", { src: fileUrl(id), controls: true, autoplay: true, playsinline: true }));
  }

  function update(): void {
    const id = currentId();
    if (id === null || !state.viewer) return;
    const item = state.byId.get(id);
    if (!item) return;

    resetZoom(false);
    if (item.kind === "video") showVideo(id);
    else showImage(id, item.name);
    liveBtn.classList.toggle("hidden", !(item.kind === "image" && item.live_video_id));

    vDate.textContent = `${dayLabel(item.created_ts)} at ${timeLabel(item.created_ts)}`;
    vPos.textContent = `${countFmt(state.viewer.index + 1)} of ${countFmt(state.viewer.ids.length)}`;
    patchFav(id);
    downloadLink.href = fileUrl(id);
    downloadLink.setAttribute("download", item.name);
    prevBtn.disabled = state.viewer.index === 0;
    nextBtn.disabled = state.viewer.index >= state.viewer.ids.length - 1;

    const viewerIds = state.viewer.ids;
    const sameIds = filmIds !== null && filmIds.length === viewerIds.length && filmIds.every((v, i) => v === viewerIds[i]);
    if (!sameIds) {
      filmIds = [...viewerIds];
      buildFilmstrip(filmIds);
      stripSlot.replaceChildren(filmWrap!);
    }
    syncFilmstrip(state.viewer.index);

    void markViewed(id);
    if (infoOpen) info.show(id);
    viewerHooks.onShow?.(id);
  }

  filmStep = (idx: number) => {
    if (!state.viewer) return;
    state.viewer.index = idx;
    update();
  };

  function render(): void {
    const id = currentId();
    if (id === null) {
      if (root) {
        root.classList.remove("open");
        const dead = root;
        setTimeout(() => dead.remove(), 170);
        root = null;
      }
      filmIds = null;
      filmTrack = null;
      filmWrap = null;
      infoOpen = false;
      if (savedScroll) {
        const { el, top } = savedScroll;
        savedScroll = null;
        requestAnimationFrame(() => {
          el.scrollTop = top;
        });
      }
      return;
    }
    if (!root) build();
    update();
  }

  window.addEventListener("keydown", (event) => {
    if (!state.viewer) return;
    const shown = currentId();
    if (shown !== null && viewerHooks.keys.some((fn) => fn(event, shown))) return;
    if (event.key === "Escape") closeViewer();
    if (event.key === "ArrowLeft") stepViewer(-1);
    if (event.key === "ArrowRight") stepViewer(1);
    if (shown !== null && ratingKey(event, [shown])) event.preventDefault();
  });

  on("viewer", render);
  on("meta", () => {
    const id = currentId();
    if (root && id !== null && patched.ids.includes(id)) patchFav(id);
  });
}
