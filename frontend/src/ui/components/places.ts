import { api } from "../../engine/api.js";
import { countFmt, dayLabel, fullStamp } from "../../engine/format.js";
import { invalidateMedia, navigate, on, patchMedia, state, type QuerySpec } from "../../engine/store.js";
import type { Media } from "../../engine/types.js";
import type { CtxEntry } from "../contextmenu.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { openModal } from "../modal.js";
import { toast } from "../toast.js";
import { loadThumb, tileHooks } from "./grid.js";
import { createMap, type MapPoint } from "./map.js";
import { specHash } from "./organize.js";
import { coverCard } from "./pages.js";
import { selectbarExtras } from "./selectbar.js";
import { viewerHooks } from "./viewer.js";

interface CountryRow { country: string; count: number; lat: number; lon: number; cover: number | null }
interface CityRow extends CountryRow { place: string; admin: string | null }
interface Trip { key: string; title: string; country: string; start_ts: number; end_ts: number; days: number; count: number; ids: number[] }
interface SearchHit { name: string; admin: string | null; country: string; lat: number; lon: number }
interface LocatedItem { id: number; lat: number | null; lon: number | null; place: string | null; admin: string | null; country: string | null }

function idsSpec(ids: number[], title: string): string {
  return specHash({ rules: [{ field: "ids", value: ids.slice(0, 5000) }], sort: "newest", title } as QuerySpec);
}

function tripHash(trip: Trip): string {
  return specHash({ rules: [{ field: "created", op: "between", value: [trip.start_ts, trip.end_ts + 1] }], sort: "oldest", title: trip.title } as QuerySpec);
}

function tripCovers(trip: Trip): number[] {
  if (trip.ids.length <= 4) return trip.ids;
  const step = trip.ids.length / 4;
  return [0, 1, 2, 3].map((i) => trip.ids[Math.floor(i * step)]);
}

function tripRange(trip: Trip): string {
  const a = dayLabel(trip.start_ts);
  const b = dayLabel(trip.end_ts);
  return a === b ? a : `${a} to ${b}`;
}

function stripCard(coverId: number | null, label: string, sub: string, hash: string): HTMLElement {
  const img = h("img", { alt: "", draggable: false }) as HTMLImageElement;
  if (coverId !== null) loadThumb(img, coverId, 384);
  const card = h("div", { class: "strip-card" }, h("div", { class: "strip-cover" }, img), h("div", { class: "strip-label" }, label), h("div", { class: "strip-sub" }, sub));
  card.addEventListener("click", () => navigate(hash));
  return card;
}

function emptyCard(icon: "map" | "place", title: string, sub: string): HTMLElement {
  return h("div", { class: "empty-center hidden" }, h("div", { class: "empty-card glass-panel" }, iconEl(icon), h("span", { class: "empty-title" }, title), h("span", { class: "empty-sub" }, sub)));
}

export function tripsStrip(container: HTMLElement): () => void {
  let alive = true;
  const empty = emptyCard("map", "No Trips Yet", "Trips appear when located photos are taken far from home over a few days.");
  const strip = h("div", { class: "strip" });
  container.append(strip, empty);
  const refresh = () => void api<{ trips: Trip[] }>("/trips").then((res) => {
    if (!alive) return;
    empty.classList.toggle("hidden", res.trips.length > 0);
    patchList(strip, res.trips.slice(0, 24), (t) => t.key, (t) => stripCard(t.ids[0] ?? null, t.title, tripRange(t), tripHash(t)),
      (node, t) => setText(node.querySelector(".strip-sub") as HTMLElement, tripRange(t)));
  });
  refresh();
  const off = on("summary", refresh);
  return () => {
    alive = false;
    off();
  };
}

export function placesStrip(container: HTMLElement): () => void {
  let alive = true;
  const empty = emptyCard("place", "No Places Yet", "Photos with GPS data appear here by city and country.");
  const strip = h("div", { class: "strip" });
  container.append(strip, empty);
  const refresh = () => void api<{ cities: CityRow[] }>("/places").then((res) => {
    if (!alive) return;
    empty.classList.toggle("hidden", res.cities.length > 0);
    patchList(strip, res.cities.slice(0, 24), (c) => `${c.place}|${c.country}`, (c) => stripCard(c.cover, c.place, `${c.country} · ${countFmt(c.count)}`,
      specHash({ rules: [{ field: "place", op: "contains", value: c.place }], title: c.place } as QuerySpec)),
    (node, c) => setText(node.querySelector(".strip-sub") as HTMLElement, `${c.country} · ${countFmt(c.count)}`));
  });
  refresh();
  const off = on("summary", refresh);
  return () => {
    alive = false;
    off();
  };
}

export function mountPlacesPage(host: HTMLElement): () => void {
  const map = createMap({ onOpen: (ids) => navigate(idsSpec(ids, "Places")), onMove: () => syncInView() });
  const inView = h("button", { class: "btn map-inview", type: "button" }, iconEl("grid"), h("span", { class: "inview-label" }, "Show Items in View"));
  inView.addEventListener("click", () => {
    const [s, w, n, e] = map.bounds();
    navigate(specHash({ rules: [{ field: "bbox", value: [s, w, n, e] }], title: "Map Area" } as QuerySpec));
  });
  const tabs = h("div", { class: "seg" });
  const grid = h("div", { class: "month-grid" });
  let tab: "cities" | "countries" = "cities";
  let data: { countries: CountryRow[]; cities: CityRow[] } = { countries: [], cities: [] };
  for (const [key, label] of [["cities", "Cities"], ["countries", "Countries"]] as const) {
    const btn = h("button", { class: `seg-btn${key === tab ? " active" : ""}`, type: "button" }, label);
    btn.dataset.key = key;
    btn.addEventListener("click", () => {
      tab = key;
      tabs.querySelectorAll<HTMLElement>(".seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.key === key));
      paintGrid();
    });
    tabs.append(btn);
  }
  const empty = emptyCard("place", "No Located Photos", "Items with GPS data, or a location you add, appear on the map.");
  host.append(h("div", { class: "view-pad places-page" },
    h("div", { class: "map-frame glass-panel" }, map.el, inView),
    h("div", { class: "section-head" }, h("h2", {}, "Places"), h("span", { class: "head-spacer" }), tabs),
    grid, empty,
    h("div", { class: "field-hint map-credit" }, "Place data from GeoNames (geonames.org), CC BY 4.0. Country outlines from Natural Earth.")));

  function paintGrid(): void {
    const rows = tab === "cities"
      ? data.cities.map((r) => ({ k: `c:${r.place}|${r.country}`, title: r.place, sub: [r.admin, r.country].filter(Boolean).join(", "), count: r.count, cover: r.cover }))
      : data.countries.map((r) => ({ k: `n:${r.country}`, title: r.country, sub: "", count: r.count, cover: r.cover }));
    patchList(grid, rows, (r) => r.k, (r) => coverCard(r.title, `${r.sub ? `${r.sub} · ` : ""}${countFmt(r.count)} items`, r.cover !== null ? [r.cover] : [],
      specHash({ rules: [{ field: "place", op: "contains", value: r.title }], title: r.title } as QuerySpec)));
  }

  let inViewTimer = 0;
  function syncInView(): void {
    window.clearTimeout(inViewTimer);
    inViewTimer = window.setTimeout(() => {
      const [s, w, n, e] = map.bounds();
      void api<{ count: number }>(`/browse/count?spec=${encodeURIComponent(JSON.stringify({ rules: [{ field: "bbox", value: [s, w, n, e] }] }))}`)
        .then((res) => setText(inView.querySelector(".inview-label") as HTMLElement, `Show ${countFmt(res.count)} in View`));
    }, 220);
  }

  let alive = true;
  void Promise.all([api<{ points: MapPoint[] }>("/places/points"), api<{ countries: CountryRow[]; cities: CityRow[] }>("/places")]).then(([pts, summary]) => {
    if (!alive) return;
    map.setPoints(pts.points);
    map.fit();
    data = summary;
    empty.classList.toggle("hidden", pts.points.length > 0);
    paintGrid();
    syncInView();
  });
  return () => {
    alive = false;
    window.clearTimeout(inViewTimer);
    map.destroy();
  };
}

export function mountTripsPage(host: HTMLElement): () => void {
  const grid = h("div", { class: "month-grid" });
  const empty = emptyCard("map", "No Trips Yet", "Trips appear when located photos are taken far from home over a few days.");
  host.append(h("div", { class: "view-pad" }, grid, empty));
  let alive = true;
  void api<{ trips: Trip[] }>("/trips").then((res) => {
    if (!alive) return;
    empty.classList.toggle("hidden", res.trips.length > 0);
    patchList(grid, res.trips, (t) => t.key, (t) => coverCard(t.title, `${tripRange(t)} · ${t.days} day${t.days === 1 ? "" : "s"} · ${countFmt(t.count)} items`, tripCovers(t), tripHash(t)));
  });
  return () => {
    alive = false;
  };
}

function applyLocated(items: LocatedItem[]): void {
  for (const item of items) patchMedia([item.id], { lat: item.lat, lon: item.lon, place: item.place, admin: item.admin, country: item.country } as Partial<Media>);
  viewerHooks.refreshInfo?.();
}

export function locationFlow(ids: number[]): void {
  const first = state.byId.get(ids[0]);
  const modal = openModal(ids.length === 1 ? "Adjust Location" : `Location for ${countFmt(ids.length)} Items`, 560);
  const search = h("input", { class: "field-input", placeholder: "Search a city, or paste coordinates like 48.8584, 2.2945", spellcheck: "false", autocomplete: "off" }) as HTMLInputElement;
  search.addEventListener("keydown", (event) => event.stopPropagation());
  const results = h("div", { class: "loc-results" });
  const chosen = h("div", { class: "loc-chosen" }, "No location chosen");
  let pick: { lat: number; lon: number } | null = first?.lat != null && first?.lon != null ? { lat: first.lat, lon: first.lon } : null;
  const map = createMap({ markers: false, onPick: (lat, lon) => choose(lat, lon) });
  const frame = h("div", { class: "map-frame small" }, map.el);

  let labelSeq = 0;
  function choose(lat: number, lon: number, label?: string): void {
    pick = { lat, lon };
    map.setPin(lat, lon);
    const coords = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    const seq = ++labelSeq;
    setText(chosen, label ? `${label}\n${coords}` : coords);
    if (!label) {
      void api<{ place: string | null; admin: string | null; country: string | null }>(`/places/reverse?lat=${lat}&lon=${lon}`).then((r) => {
        if (seq !== labelSeq) return;
        const name = [r.place, r.admin, r.country].filter(Boolean).join(", ");
        if (name) setText(chosen, `${name}\n${coords}`);
      });
    }
  }

  let searchTimer = 0;
  let searchSeq = 0;
  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    const text = search.value.trim();
    const coords = text.match(/^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/);
    if (coords) {
      const lat = Number(coords[1]);
      const lon = Number(coords[2]);
      if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
        choose(lat, lon);
        map.center(lat, lon, 10);
        patchList(results, [], () => "", () => h("div", {}));
      }
      return;
    }
    searchTimer = window.setTimeout(() => {
      const seq = ++searchSeq;
      void api<{ results: SearchHit[] }>(`/places/search?text=${encodeURIComponent(text)}`).then((res) => {
        if (seq !== searchSeq) return;
        patchList(results, res.results, (r) => `${r.name}|${r.lat}|${r.lon}`, (r) => {
          const label = [r.name, r.admin, r.country].filter(Boolean).join(", ");
          const row = h("button", { class: "loc-row", type: "button" }, iconEl("place"), h("span", {}, label));
          row.addEventListener("click", () => {
            choose(r.lat, r.lon, label);
            map.center(r.lat, r.lon, 10);
          });
          return row;
        });
      });
    }, 140);
  });

  const hidden = ids.every((id) => state.byId.get(id)?.location_hidden);
  const hideBtn = h("button", { class: "btn", type: "button" }, hidden ? "Show Location" : "Hide Location");
  hideBtn.addEventListener("click", async () => {
    await api("/media/location-hidden", { method: "POST", body: JSON.stringify({ ids, hidden: !hidden }) });
    patchMedia(ids, { location_hidden: hidden ? 0 : 1 } as Partial<Media>);
    viewerHooks.refreshInfo?.();
    toast(hidden ? "Location shown" : "Location hidden from Places and shares");
    modal.close();
  });
  const removeBtn = h("button", { class: "btn danger", type: "button" }, "Remove Location");
  removeBtn.addEventListener("click", async () => {
    const res = await api<{ items: LocatedItem[] }>("/media/location", { method: "POST", body: JSON.stringify({ ids, lat: null, lon: null }) });
    applyLocated(res.items);
    toast("Location removed");
    modal.close();
  });
  const cancel = h("button", { class: "btn", type: "button" }, "Cancel");
  cancel.addEventListener("click", modal.close);
  const save = h("button", { class: "btn primary", type: "button" }, "Save");
  save.addEventListener("click", async () => {
    if (!pick) {
      toast("Choose a place first");
      return;
    }
    const res = await api<{ items: LocatedItem[] }>("/media/location", { method: "POST", body: JSON.stringify({ ids, lat: pick.lat, lon: pick.lon }) });
    applyLocated(res.items);
    toast(ids.length === 1 ? "Location saved" : `Location saved for ${countFmt(ids.length)} items`);
    modal.close();
  });
  modal.body.append(search, results, frame, chosen,
    h("div", { class: "modal-foot" }, removeBtn, hideBtn, h("span", { class: "head-spacer" }), cancel, save));
  if (pick) {
    const place = [first?.place, first?.country].filter(Boolean).join(", ");
    choose(pick.lat, pick.lon, place || undefined);
    map.center(pick.lat, pick.lon, 9);
  } else {
    map.fit([]);
  }
  requestAnimationFrame(() => search.focus());
  const observer = new MutationObserver(() => {
    if (!modal.root.isConnected) {
      map.destroy();
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true });
}

function localInput(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function dateFlow(ids: number[]): void {
  const items = ids.map((id) => state.byId.get(id)).filter(Boolean) as Media[];
  const earliest = items.length ? Math.min(...items.map((m) => m.created_ts)) : Date.now() / 1000;
  const modal = openModal(ids.length === 1 ? "Adjust Date and Time" : `Adjust Date for ${countFmt(ids.length)} Items`, 440);
  const mode = h("div", { class: "seg" });
  let current: "set" | "shift" | "revert" = "set";
  const setPane = h("div", { class: "date-pane" });
  const when = h("input", { class: "field-input", type: "datetime-local", step: "1" }) as HTMLInputElement;
  when.value = localInput(earliest);
  when.addEventListener("keydown", (event) => event.stopPropagation());
  setPane.append(h("label", { class: "field" }, h("span", { class: "field-label" }, ids.length > 1 ? "Earliest item becomes" : "Date and time"), when),
    h("div", { class: "field-hint" }, ids.length > 1 ? "Other items keep their spacing from the earliest one." : `Currently ${fullStamp(earliest)}`));
  const shiftPane = h("div", { class: "date-pane row-gap hidden" });
  const unit = (label: string) => {
    const el = h("input", { class: "field-input", type: "number", step: "1", value: "0" }) as HTMLInputElement;
    el.addEventListener("keydown", (event) => event.stopPropagation());
    shiftPane.append(h("label", { class: "field" }, h("span", { class: "field-label" }, label), el));
    return el;
  };
  const days = unit("Days");
  const hours = unit("Hours");
  const minutes = unit("Minutes");
  const revertPane = h("div", { class: "date-pane hidden field-hint" }, "Restore the capture date read from the file, undoing earlier adjustments.");
  const panes = { set: setPane, shift: shiftPane, revert: revertPane };
  for (const [key, label] of [["set", "Set"], ["shift", "Shift"], ["revert", "Revert"]] as const) {
    const btn = h("button", { class: `seg-btn${key === current ? " active" : ""}`, type: "button" }, label);
    btn.addEventListener("click", () => {
      current = key;
      mode.querySelectorAll(".seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
      for (const [k, pane] of Object.entries(panes)) pane.classList.toggle("hidden", k !== key);
    });
    mode.append(btn);
  }
  const cancel = h("button", { class: "btn", type: "button" }, "Cancel");
  cancel.addEventListener("click", modal.close);
  const save = h("button", { class: "btn primary", type: "button" }, "Adjust");
  save.addEventListener("click", async () => {
    const body: Record<string, unknown> = { ids, mode: current };
    if (current === "set") {
      const ts = new Date(when.value).getTime() / 1000;
      if (!Number.isFinite(ts)) {
        toast("Pick a valid date");
        return;
      }
      body.ts = ts;
    } else if (current === "shift") {
      body.delta_s = (Number(days.value) || 0) * 86400 + (Number(hours.value) || 0) * 3600 + (Number(minutes.value) || 0) * 60;
    }
    const res = await api<{ items: Array<{ id: number; created_ts: number }> }>("/media/dates", { method: "POST", body: JSON.stringify(body) });
    for (const item of res.items) patchMedia([item.id], { created_ts: item.created_ts, created_src: current === "revert" ? "exif" : "adjusted" } as Partial<Media>);
    viewerHooks.refreshInfo?.();
    if (!state.viewer) invalidateMedia();
    toast(res.items.length ? `Adjusted ${countFmt(res.items.length)} item${res.items.length === 1 ? "" : "s"}` : "Nothing to revert");
    modal.close();
  });
  modal.body.append(mode, setPane, shiftPane, revertPane, h("div", { class: "modal-foot" }, h("span", { class: "head-spacer" }), cancel, save));
}

let copied: number | null = null;

function placeEntries(item: Media): CtxEntry[] {
  const ids = state.selection.has(item.id) && state.selection.size > 1 ? [...state.selection] : [item.id];
  const entries: CtxEntry[] = [
    { label: "Adjust Location...", icon: "place", action: () => locationFlow(ids) },
    { label: "Adjust Date and Time...", icon: "clock", action: () => dateFlow(ids) },
  ];
  if (item.lat != null) entries.push({ label: "Copy Location", icon: "copy", action: () => { copied = item.id; toast("Location copied"); } });
  if (copied !== null && copied !== item.id) {
    const source = copied;
    entries.push({ label: "Paste Location", icon: "place", action: async () => {
      const res = await api<{ items: LocatedItem[] }>("/media/location", { method: "POST", body: JSON.stringify({ ids, copy_from: source }) });
      applyLocated(res.items);
      toast(`Location pasted to ${countFmt(ids.length)} item${ids.length === 1 ? "" : "s"}`);
    } });
  }
  return entries;
}

let registered = false;

export function registerPlaces(): void {
  if (registered) return;
  registered = true;
  viewerHooks.editLocation = (id) => locationFlow([id]);
  viewerHooks.editDate = (id) => dateFlow([id]);
  tileHooks.ctx.push(placeEntries);
  selectbarExtras.push(
    { label: "Location", icon: "place", handler: (ids) => locationFlow(ids) },
    { label: "Date", icon: "clock", handler: (ids) => dateFlow(ids) },
  );
}
