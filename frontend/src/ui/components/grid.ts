import { api, fileUrl, thumbUrl } from "../../engine/api.js";
import { countFmt, dayKey, dayLabel, formatDuration, monthLabel } from "../../engine/format.js";
import {
  dropFromCaches, loadMore, on, openViewer, pageFor, periodSummary, setFavorite, setGrouping, setSelected, specFor, state, toggleSelect, trashMedia,
} from "../../engine/store.js";
import type { FilterName, Media } from "../../engine/types.js";
import { h } from "../dom.js";
import { type CtxEntry, openContextMenu } from "../contextmenu.js";
import { attachMarquee } from "../marquee.js";
import { toast } from "../toast.js";
import { addToAlbumFlow } from "./selectbar.js";
import { iconEl } from "../icons.js";

// Deterministic 13-row preload. IntersectionObserver failed three ways on real
// WKWebView (null roots, the lazy-attr veto, opaque callback scheduling), so
// thumbs are now loaded by arithmetic: each .view scroller keeps a lane of
// pending imgs w/ cached offsets, & every scroll frame loads exactly what sits
// within lookaheadPx() above & below the viewport. Offsets recompute only when
// a lane is marked dirty (adoption, zoom, resize); the 13-row slack absorbs
// small FLIP shifts between marks.
interface ThumbLane { pending: Set<HTMLImageElement>; dirty: boolean; queued: boolean }
const lanes = new Map<Element, ThumbLane>();
const thumbTops = new WeakMap<HTMLImageElement, number>();
const awaitingAttach = new Set<HTMLImageElement>();
let sweepQueued = false;
let resizeHooked = false;

// Bounded, distance-ordered fetch pipeline. WKWebView funnels every thumb
// through ~6 loopback connections, so an unbounded 13-row burst queues stale
// requests AHEAD of what the user is about to see: assignment order, not
// assignment time, is what kills the preload. Only in-window images occupy the
// queue, nearest-first, & each sweep rebuilds their order from live distances.
const MAX_FLIGHT = 14;
let inFlight = 0;
let loadQueue: { img: HTMLImageElement; dist: number }[] = [];

const loadTimes: number[] = [];

function startLoad(img: HTMLImageElement): void {
  const src = img.dataset.thumbSrc;
  if (!src || img.getAttribute("src")) return;
  inFlight += 1;
  const t0 = performance.now();
  let settled = false;
  const done = () => {
    if (settled) return;
    settled = true;
    window.clearTimeout(watchdog);
    loadTimes.push(performance.now() - t0);
    if (loadTimes.length > 20) loadTimes.shift();
    inFlight -= 1;
    pumpQueue();
  };
  const watchdog = window.setTimeout(done, 12000);
  img.addEventListener("load", done, { once: true });
  img.addEventListener("error", done, { once: true });
  img.src = src;
}

function pumpQueue(): void {
  while (inFlight < MAX_FLIGHT && loadQueue.length > 0) {
    const next = loadQueue.shift();
    if (!next) break;
    if (next.img.getAttribute("src")) continue;
    startLoad(next.img);
  }
}

function lookaheadPx(): number {
  return Math.round((state.zoom + 12) * 13);
}

function markAllDirty(): void {
  for (const [root, lane] of lanes) {
    lane.dirty = true;
    scheduleLane(root);
  }
}

// Heartbeat: the preload must not depend on any event hook firing. A 300ms
// pulse sweeps every lane (cheap compares) & a 2s pulse re-measures offsets,
// so even w/ every scroll/adoption/resize listener dead the 13-row runway
// still fills itself.
let beat = 0;
window.setInterval(() => {
  beat += 1;
  for (const [root, lane] of lanes) {
    if (!root.isConnected) {
      lanes.delete(root);
      continue;
    }
    if (beat % 7 === 0) lane.dirty = true;
    scheduleLane(root);
  }
}, 300);

let hudEl: HTMLElement | null = null;
let hudOn = false;

export function setPreloadHud(on: boolean): void {
  hudOn = on;
  if (!on && hudEl) {
    hudEl.remove();
    hudEl = null;
  }
}

function updateHud(stats: { pending: number; queued: number; ahead: number; behind: number }): void {
  if (!hudOn) return;
  if (!hudEl) {
    hudEl = h("div", { class: "preload-hud" });
    document.body.append(hudEl);
  }
  const avg = loadTimes.length ? Math.round(loadTimes.reduce((a, b) => a + b, 0) / loadTimes.length) : 0;
  hudEl.textContent = `pend ${stats.pending} · q ${stats.queued} · fly ${inFlight} · ahead ${Math.round(stats.ahead)}px · behind ${Math.round(stats.behind)}px · load ${avg}ms`;
}

function laneFor(root: Element): ThumbLane {
  let lane = lanes.get(root);
  if (!lane) {
    lane = { pending: new Set(), dirty: true, queued: false };
    lanes.set(root, lane);
    root.addEventListener("scroll", () => scheduleLane(root), { passive: true });
    if (!resizeHooked) {
      resizeHooked = true;
      window.addEventListener("resize", markAllDirty);
    }
  }
  return lane;
}

function scheduleLane(root: Element): void {
  const lane = lanes.get(root);
  if (!lane || lane.queued) return;
  lane.queued = true;
  requestAnimationFrame(() => {
    lane.queued = false;
    sweepLane(root, lane);
  });
}

function sweepLane(root: Element, lane: ThumbLane): void {
  if (!root.isConnected) {
    lanes.delete(root);
    return;
  }
  if (lane.pending.size === 0) return;
  const rootRect = root.getBoundingClientRect();
  const scrollTop = root.scrollTop;
  if (lane.dirty) {
    for (const img of lane.pending) {
      if (!img.isConnected) continue;
      thumbTops.set(img, img.getBoundingClientRect().top - rootRect.top + scrollTop);
    }
    lane.dirty = false;
  }
  const ahead = lookaheadPx();
  const lo = scrollTop - ahead;
  const viewBottom = scrollTop + root.clientHeight;
  const hi = viewBottom + ahead;
  const candidates: { img: HTMLImageElement; dist: number }[] = [];
  let firstUnloadedBelow = Infinity;
  let firstUnloadedAbove = -Infinity;
  for (const img of [...lane.pending]) {
    if (!img.isConnected) {
      lane.pending.delete(img);
      continue;
    }
    if (img.getAttribute("src")) {
      lane.pending.delete(img);
      continue;
    }
    const top = thumbTops.get(img);
    if (top === undefined) {
      lane.pending.delete(img);
      startLoad(img);
      continue;
    }
    if (top > viewBottom && top < firstUnloadedBelow) firstUnloadedBelow = top;
    if (top < scrollTop && top > firstUnloadedAbove) firstUnloadedAbove = top;
    if (top >= lo && top <= hi) {
      const dist = top < scrollTop ? scrollTop - top : top > viewBottom ? top - viewBottom : 0;
      candidates.push({ img, dist });
    }
  }
  candidates.sort((a, b) => a.dist - b.dist);
  const mine = new Set(candidates.map((c) => c.img));
  loadQueue = [...candidates, ...loadQueue.filter((e) => !mine.has(e.img) && !lane.pending.has(e.img) && !e.img.getAttribute("src"))];
  pumpQueue();
  updateHud({
    pending: lane.pending.size,
    queued: loadQueue.length,
    ahead: Math.min(ahead, firstUnloadedBelow - viewBottom),
    behind: Math.min(ahead, scrollTop - firstUnloadedAbove),
  });
}

function scrollerFor(el: Element): Element | null {
  return el.closest(".view");
}

// Tiles are built detached & appended in batches, so closest(".view") can be null
// for several frames. Retry, then adopt into the scroller's lane.
function sweepAwaiting(framesLeft: number): void {
  sweepQueued = false;
  const touched = new Set<Element>();
  for (const img of [...awaitingAttach]) {
    if (img.getAttribute("src")) {
      awaitingAttach.delete(img);
      continue;
    }
    const root = scrollerFor(img);
    if (root) {
      awaitingAttach.delete(img);
      laneFor(root).pending.add(img);
      touched.add(root);
    }
  }
  for (const root of touched) {
    const lane = lanes.get(root);
    if (lane) lane.dirty = true;
    scheduleLane(root);
  }
  if (awaitingAttach.size === 0) return;
  if (framesLeft > 0) {
    sweepQueued = true;
    requestAnimationFrame(() => sweepAwaiting(framesLeft - 1));
    return;
  }
  // Never leave a tile permanently blank: load whatever is still homeless.
  for (const img of awaitingAttach) {
    startLoad(img);
  }
  awaitingAttach.clear();
}

export function loadImage(img: HTMLImageElement, src: string): void {
  img.decoding = "async";
  img.loading = "eager";
  img.dataset.thumbSrc = src;
  markWaiting(img);
  img.addEventListener("load", () => revealLoaded(img), { once: true });
  img.addEventListener("error", () => img.classList.add("broken", "ready"), { once: true });
  observeThumb(img);
}

function observeThumb(img: HTMLImageElement): void {
  if (img.getAttribute("src")) return;
  const root = scrollerFor(img);
  if (root) {
    const lane = laneFor(root);
    lane.pending.add(img);
    lane.dirty = true;
    scheduleLane(root);
    return;
  }
  awaitingAttach.add(img);
  if (!sweepQueued) {
    sweepQueued = true;
    requestAnimationFrame(() => sweepAwaiting(40));
  }
}

export function resetThumbLookahead(): void {
  markAllDirty();
}

on("media", markAllDirty);

function markWaiting(img: HTMLImageElement): void {
  requestAnimationFrame(() => {
    if (!img.classList.contains("ready")) {
      img.closest(".tile, .strip-cover")?.classList.add("thumb-wait");
    }
  });
}

function revealLoaded(img: HTMLImageElement): void {
  img.classList.add("ready");
  img.closest(".tile, .strip-cover")?.classList.remove("thumb-wait");
}

export function loadThumb(img: HTMLImageElement, mediaId: number, size: number): void {
  img.decoding = "async";
  img.loading = "eager";
  img.dataset.thumbSrc = thumbUrl(mediaId, size);
  markWaiting(img);
  img.addEventListener("load", () => revealLoaded(img), { once: true });
  img.addEventListener("error", () => img.classList.add("broken", "ready"), { once: true });
  observeThumb(img);
}

export function tileFor(item: Media, context: () => number[], selectable = true, extraCtx?: (item: Media) => CtxEntry[]): HTMLElement {
  const img = h("img", { alt: item.name, loading: "lazy", draggable: false }) as HTMLImageElement;
  loadThumb(img, item.id, 384);
  const badges = h("div", { class: "tile-badges" });
  if (item.favorite) badges.append(iconEl("heartFill"));
  if (item.kind === "video") badges.append(iconEl("video"));
  if (item.kind === "image" && item.live_video_id) badges.append(h("span", { class: "live-chip" }, "LIVE"));
  const parts: HTMLElement[] = [img, badges];
  if (item.kind === "video" && item.duration) {
    parts.push(h("span", { class: "tile-duration" }, formatDuration(item.duration)));
  }
  const tile = h("div", { class: "tile", "data-id": String(item.id) }, ...parts);
  tile.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const live = state.byId.get(item.id) ?? item;
    openContextMenu(event.clientX, event.clientY, [
      { label: "Open", icon: "eye", action: () => openViewer(context(), context().indexOf(item.id)) },
      { label: live.favorite ? "Unfavorite" : "Favorite", icon: "heart", action: () => void setFavorite(item.id, !live.favorite) },
      { label: "Add to Album...", icon: "albums", action: () => addToAlbumFlow([item.id]) },
      ...(extraCtx ? extraCtx(item) : []),
      { label: "Download", icon: "download", action: () => { const a = h("a", { href: fileUrl(item.id), download: live.name }); a.click(); } },
      "sep",
      { label: "Hide", icon: "eyeOff", action: async () => { await api(`/media/${item.id}/hide`, { method: "POST" }); dropFromCaches(item.id); toast("Hidden"); } },
      { label: "Move to Trash", icon: "trash", danger: true, action: () => void trashMedia(item.id) },
    ]);
  });
  if (item.kind === "video") {
    tile.append(h("span", { class: "kind-mark", title: "Video" }, iconEl("video")));
    let preview: HTMLVideoElement | null = null;
    tile.addEventListener("mouseenter", () => {
      if (preview) return;
      preview = h("video", {
        class: "tile-preview", src: fileUrl(item.id), muted: true, loop: true, playsinline: true, preload: "metadata",
      }) as HTMLVideoElement;
      preview.muted = true;
      tile.insertBefore(preview, badges);
      void preview.play().catch(() => undefined);
    });
    tile.addEventListener("mouseleave", () => {
      if (!preview) return;
      preview.pause();
      preview.remove();
      preview = null;
    });
  }
  if (selectable) {
    const check = h("button", { class: "tile-check", type: "button", "aria-label": "Select" }, iconEl("check"));
    check.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleSelect(item.id);
    });
    tile.append(check);
  }
  tile.addEventListener("click", () => {
    if (state.selection.size > 0 && selectable) {
      toggleSelect(item.id);
      return;
    }
    const ids = context();
    openViewer(ids, ids.indexOf(item.id));
  });
  tile.classList.toggle("selected", state.selection.has(item.id));
  return tile;
}

export function mountGrid(host: HTMLElement, filter: FilterName, showControls: boolean): () => void {
  const gridWrap = h("div", {});
  const sentinel = h("div", { class: "load-sentinel" });
  const pad = h("div", { class: "view-pad" }, gridWrap, sentinel);
  pad.style.setProperty("--tile", `${state.zoom}px`);
  host.append(pad);

  const rendered = new Map<number, HTMLElement>();
  const dayNodes = new Map<string, { section: HTMLElement; grid: HTMLElement; count: HTMLElement; n: number }>();
  let monthMode = false;

  function context(): number[] {
    return pageFor(filter).items.map((m) => m.id);
  }

  function groupOf(item: Media): { key: string; label: string } {
    const sort = specFor(filter).sort ?? "newest";
    if (sort === "newest" || sort === "oldest") return { key: dayKey(item.created_ts), label: dayLabel(item.created_ts) };
    if (sort === "added" || sort === "added_oldest") return { key: `a${dayKey(item.imported_ts)}`, label: `Added ${dayLabel(item.imported_ts)}` };
    return { key: "all", label: "" };
  }

  function ensureDay(key: string, label: string): { section: HTMLElement; grid: HTMLElement; count: HTMLElement; n: number } {
    let entry = dayNodes.get(key);
    if (!entry) {
      const count = h("span", { class: "day-count" }, "");
      const grid = h("div", { class: "tile-grid" });
      const section = h("section", {}, h("div", { class: "day-head" }, h("h3", {}, label), count), grid);
      entry = { section, grid, count, n: 0 };
      dayNodes.set(key, entry);
      gridWrap.append(section);
    }
    return entry;
  }

  let appendCursor = 0;
  let appendScheduled = false;

  function appendItems(): void {
    if (monthMode) return;
    const page = pageFor(filter);
    const ids = new Set(page.items.map((m) => m.id));
    let pruned = false;
    for (const [id, node] of rendered) {
      if (!ids.has(id)) {
        slideOutAndRemove(node);
        rendered.delete(id);
        pruned = true;
      }
    }
    if (pruned) {
      appendCursor = Math.min(appendCursor, page.items.length);
      for (const [key, entry] of dayNodes) {
        const remaining = entry.grid.querySelectorAll(".tile:not(.removing)").length;
        entry.n = remaining;
        entry.count.textContent = countFmt(remaining);
        if (remaining === 0) {
          window.setTimeout(() => entry.section.remove(), 220);
          dayNodes.delete(key);
        }
      }
    } else if (appendCursor > page.items.length) {
      for (const entry of dayNodes.values()) entry.section.remove();
      dayNodes.clear();
      for (const node of rendered.values()) node.remove();
      rendered.clear();
      appendCursor = 0;
    }
    if (appendScheduled) return;
    appendScheduled = true;
    const step = () => {
      const items = pageFor(filter).items;
      const chunkEnd = Math.min(appendCursor + 80, items.length);
      const fragments = new Map<string, DocumentFragment>();
      for (; appendCursor < chunkEnd; appendCursor++) {
        const item = items[appendCursor];
        if (rendered.has(item.id)) continue;
        const group = groupOf(item);
        const key = group.key;
        const entry = ensureDay(key, group.label);
        let frag = fragments.get(key);
        if (!frag) {
          frag = document.createDocumentFragment();
          fragments.set(key, frag);
        }
        const tile = tileFor(item, context);
        frag.append(tile);
        rendered.set(item.id, tile);
        entry.n += 1;
        entry.count.textContent = countFmt(entry.n);
      }
      for (const [key, frag] of fragments) dayNodes.get(key)!.grid.append(frag);
      if (appendCursor < pageFor(filter).items.length) {
        requestAnimationFrame(step);
      } else {
        appendScheduled = false;
      }
    };
    requestAnimationFrame(step);
  }

  async function renderMonths(level: "month" | "year"): Promise<void> {
    monthMode = true;
    const data = await periodSummary(level);
    const grid = h("div", { class: "month-grid" });
    for (const period of data.periods) {
      const covers = h("div", { class: "month-covers" });
      for (const coverId of period.covers) {
        const img = h("img", { alt: "", loading: "lazy", draggable: false }) as HTMLImageElement;
        loadThumb(img, coverId, 384);
        covers.append(img);
      }
      const label = level === "year" ? period.period : monthLabel(period.period);
      const card = h(
        "div",
        { class: "month-card" },
        covers,
        h("div", { class: "month-label" }, label),
        h("div", { class: "month-count" }, `${countFmt(period.count)} items`),
      );
      card.addEventListener("click", () => setGrouping("all"));
      grid.append(card);
    }
    gridWrap.replaceChildren(grid);
  }

  function renderMode(): void {
    if (state.grouping === "all" || !showControls) {
      if (monthMode) {
        monthMode = false;
        rendered.clear();
        dayNodes.clear();
        gridWrap.replaceChildren();
      }
      appendItems();
    } else {
      rendered.clear();
      dayNodes.clear();
      void renderMonths(state.grouping === "months" ? "month" : "year");
    }
  }

  const observer = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting) && !monthMode) void loadMore(filter);
  }, { root: host.closest(".view"), rootMargin: `${Math.max(1600, lookaheadPx())}px 0px` });
  // If host was not attached yet, the observer above got the viewport root & an
  // inert margin; rebuild it against the real scroller once it exists.
  if (!host.closest(".view")) {
    requestAnimationFrame(() => {
      const root = host.closest(".view");
      if (!root) return;
      observer.disconnect();
      const rebuilt = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting) && !monthMode) void loadMore(filter);
      }, { root, rootMargin: `${Math.max(1600, lookaheadPx())}px 0px` });
      rebuilt.observe(sentinel);
      offs.push(() => rebuilt.disconnect());
    });
  }
  observer.observe(sentinel);

  const offs = [
    on("page", renderMode),
    on("grouping", renderMode),
    on("zoom", () => {
      pad.style.setProperty("--tile", `${state.zoom}px`);
      resetThumbLookahead();
    }),
    on("selection", () => {
      rendered.forEach((node, id) => node.classList.toggle("selected", state.selection.has(id)));
    }),
  ];

  let pagerDead = false;
  offs.push(() => {
    pagerDead = true;
  });
  function hookPager(): void {
    if (pagerDead) return;
    const root = host.closest(".view");
    if (!root) {
      requestAnimationFrame(hookPager);
      return;
    }
    const onScroll = () => {
      if (monthMode) return;
      if (root.scrollHeight - (root.scrollTop + root.clientHeight) < Math.max(1600, lookaheadPx())) void loadMore(filter);
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    offs.push(() => root.removeEventListener("scroll", onScroll));
    onScroll();
  }
  hookPager();

  void loadMore(filter);
  renderMode();

  return () => {
    observer.disconnect();
    offs.forEach((off) => off());
  };
}


let pinchBudget = 0;

function slideOutAndRemove(node: HTMLElement): void {
  const grid = node.parentElement;
  const siblings = grid ? [...grid.querySelectorAll<HTMLElement>(".tile")].filter((el) => el !== node) : [];
  const before = new Map(siblings.map((el) => [el, el.getBoundingClientRect()]));
  node.classList.add("removing");
  window.setTimeout(() => {
    node.remove();
    requestAnimationFrame(() => {
      for (const el of siblings) {
        const prev = before.get(el);
        if (!prev) continue;
        const now = el.getBoundingClientRect();
        const dx = prev.left - now.left;
        const dy = prev.top - now.top;
        if (dx === 0 && dy === 0) continue;
        el.style.transition = "none";
        el.style.transform = `translate(${dx}px, ${dy}px)`;
        requestAnimationFrame(() => {
          el.style.transition = "";
          el.style.transform = "";
        });
      }
    });
  }, 170);
}

export function bindSelectionClasses(container: HTMLElement): () => void {
  const sync = () => {
    for (const tile of container.querySelectorAll<HTMLElement>(".tile[data-id]")) {
      tile.classList.toggle("selected", state.selection.has(Number(tile.dataset.id)));
    }
  };
  sync();
  return on("selection", sync);
}

export function enablePinchOpen(scroller: HTMLElement): () => void {
  const onWheel = (event: WheelEvent) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    pinchBudget += -event.deltaY;
    if (pinchBudget > 90) {
      pinchBudget = 0;
      const tile = (event.target as HTMLElement).closest<HTMLElement>(".tile[data-id]");
      if (tile) {
        const id = Number(tile.dataset.id);
        const scope = tile.closest<HTMLElement>(".tile-grid");
        const ids = scope
          ? [...scope.querySelectorAll<HTMLElement>(".tile[data-id]")].map((el) => Number(el.dataset.id))
          : [id];
        openViewer(ids, Math.max(0, ids.indexOf(id)));
      }
    } else if (pinchBudget < -90) {
      pinchBudget = 0;
    }
  };
  scroller.addEventListener("wheel", onWheel, { passive: false });
  return () => scroller.removeEventListener("wheel", onWheel);
}

export function enableMarquee(container: HTMLElement): () => void {
  return attachMarquee(container, {
    itemSelector: ".tile[data-id]",
    idOf: (el) => {
      const raw = el.dataset.id;
      return raw ? Number(raw) : null;
    },
    isSelected: (id) => state.selection.has(id),
    setSelected: (id, on) => setSelected(id, on),
  });
}
