import { api, thumbUrl, thumbVersions } from "../../engine/api.js";
import { formatDuration } from "../../engine/format.js";
import { patchMedia, state as store } from "../../engine/store.js";
import type { Media } from "../../engine/types.js";
import type { CtxEntry } from "../contextmenu.js";
import { h } from "../dom.js";
import { iconEl, type IconName } from "../icons.js";
import { setText } from "../keyed.js";
import { promptText } from "../prompt.js";
import { toast } from "../toast.js";
import { tileHooks } from "./grid.js";
import { selectbarExtras } from "./selectbar.js";
import { viewerHooks } from "./viewer.js";

type Dict = Record<string, unknown>;
type Box4 = [number, number, number, number];
interface Spot { x?: number; y?: number; r?: number; points?: Array<[number, number]>; kind?: "mask" | "pixelate"; polygons?: Array<Array<[number, number]>>; box?: Box4; label?: string }
interface CleanInfo { fill: boolean; segment: boolean; suggest: boolean; faces: boolean; faces_found: Box4[] }
interface Suggestion { box: Box4; label: string; score: number }
interface EditState {
  light?: Record<string, number>;
  color?: Record<string, number>;
  detail?: Record<string, number>;
  bw?: Record<string, number>;
  filter?: { name: string; amount?: number };
  levels?: { black?: number; white?: number; gamma?: number };
  curves?: { rgb?: number[][] };
  geometry?: { rotate?: number; flipH?: boolean; flipV?: boolean; straighten?: number; crop?: { x: number; y: number; w: number; h: number } };
  retouch?: Spot[];
  markup?: Array<{ type: string; points: number[][]; color: string; width: number; text?: string; size?: number }>;
}

type Tab = "adjust" | "filters" | "crop" | "retouch" | "markup";

const SLIDERS: Array<{ group: "light" | "color" | "bw" | "detail"; title: string; rows: Array<[string, string, number, number]> }> = [
  { group: "light", title: "Light", rows: [["exposure", "Exposure", -200, 200], ["brilliance", "Brilliance", -100, 100], ["highlights", "Highlights", -100, 100],
    ["shadows", "Shadows", -100, 100], ["brightness", "Brightness", -100, 100], ["contrast", "Contrast", -100, 100], ["blacks", "Black Point", -100, 100]] },
  { group: "color", title: "Color", rows: [["saturation", "Saturation", -100, 100], ["vibrance", "Vibrance", -100, 100], ["warmth", "Warmth", -100, 100], ["tint", "Tint", -100, 100]] },
  { group: "bw", title: "Black & White", rows: [["intensity", "Intensity", 0, 100], ["tone", "Tone", -100, 100]] },
  { group: "detail", title: "Detail", rows: [["definition", "Definition", -100, 100], ["sharpen", "Sharpen", 0, 100], ["noise", "Noise Reduction", 0, 100], ["vignette", "Vignette", -100, 100]] },
];
const FILTERS: Array<[string, string]> = [["", "Original"], ["vivid", "Vivid"], ["vivid_warm", "Vivid Warm"], ["vivid_cool", "Vivid Cool"],
  ["dramatic", "Dramatic"], ["dramatic_warm", "Dramatic Warm"], ["dramatic_cool", "Dramatic Cool"], ["mono", "Mono"], ["silvertone", "Silvertone"], ["noir", "Noir"]];
const ASPECTS: Array<[string, number | null]> = [["Free", null], ["Original", -1], ["Square", 1], ["16:9", 16 / 9], ["4:3", 4 / 3], ["3:2", 3 / 2], ["5:4", 5 / 4], ["9:16", 9 / 16]];
const COLORS = ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#0a84ff", "#bf5af2", "#ffffff", "#000000"];
const SVG = "http://www.w3.org/2000/svg";

let clipboard: EditState | null = null;
let open = false;

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value ?? {})) as T;
}

function svgEl(tag: string, attrs: Record<string, string | number>): SVGElement {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

function prune(s: EditState): EditState {
  const out = clone(s) as Dict;
  for (const key of Object.keys(out)) {
    const value = out[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const obj = value as Dict;
      for (const k of Object.keys(obj)) if (obj[k] === 0 || obj[k] === false || obj[k] === null) delete obj[k];
      if (Object.keys(obj).length === 0) delete out[key];
    } else if (Array.isArray(value) && value.length === 0) {
      delete out[key];
    }
  }
  const filter = out.filter as { name?: string } | undefined;
  if (filter && !filter.name) delete out.filter;
  return out as EditState;
}

async function saveState(item: Media, next: EditState): Promise<void> {
  const res = await api<{ edit_json: string | null; edited_ts: number | null }>(`/media/${item.id}/edits`, { method: "PUT", body: JSON.stringify({ state: prune(next) }) });
  thumbVersions.set(item.id, res.edited_ts ?? Date.now() / 1000);
  patchMedia([item.id], { edit_json: res.edit_json, edited_ts: res.edited_ts } as Partial<Media>);
  viewerHooks.reloadStill?.();
}

export async function revertToOriginal(ids: number[]): Promise<void> {
  for (const id of ids) {
    const res = await api<{ edit_json: string | null; edited_ts: number | null }>(`/media/${id}/edits`, { method: "DELETE" });
    thumbVersions.set(id, Date.now() / 1000);
    patchMedia([id], { edit_json: res.edit_json, edited_ts: res.edited_ts } as Partial<Media>);
  }
  viewerHooks.reloadStill?.();
  toast(ids.length === 1 ? "Reverted to original" : `Reverted ${ids.length} items`);
}

export async function pasteEdits(ids: number[]): Promise<void> {
  if (!clipboard) return;
  const res = await api<{ items: Array<{ id: number; edit_json: string | null; edited_ts: number | null }> }>("/media/batch/edits", { method: "POST", body: JSON.stringify({ ids, state: clipboard }) });
  for (const it of res.items) {
    thumbVersions.set(it.id, it.edited_ts ?? Date.now() / 1000);
    patchMedia([it.id], { edit_json: it.edit_json, edited_ts: it.edited_ts } as Partial<Media>);
  }
  viewerHooks.reloadStill?.();
  toast(`Pasted edits to ${res.items.length} item${res.items.length === 1 ? "" : "s"}`);
}

export async function copyEdits(id: number): Promise<void> {
  const res = await api<{ state: EditState }>(`/media/${id}/edits`);
  clipboard = res.state;
  toast("Edits copied");
}

export function openEditor(item: Media): void {
  if (open) return;
  if (item.kind === "video") {
    openTrim(item);
    return;
  }
  open = true;
  let s: EditState = {};
  const undo: string[] = [];
  const redo: string[] = [];
  let tab: Tab = "adjust";
  let previewSeq = 0;
  let dragging = false;
  let inflight = false;
  let queued = false;
  let timer = 0;
  let currentUrl = "";
  let natural = { w: 1, h: 1 };
  let aspect: number | null = null;
  let tool = "pen";
  let color = COLORS[0];
  let penWidth = 0.006;
  let brush = 0.025;
  let cleanMode: "brush" | "select" = "brush";
  let cleanInfo: CleanInfo | null = null;
  let suggestions: Suggestion[] = [];
  let pendingBox: Box4 | null = null;

  const img = h("img", { class: "ed-img", alt: item.name, draggable: false }) as HTMLImageElement;
  img.src = thumbUrl(item.id, 768);
  const overlay = svgEl("svg", { class: "ed-overlay", viewBox: "0 0 1 1", preserveAspectRatio: "none" }) as SVGSVGElement;
  const frame = h("div", { class: "ed-frame" }, img, overlay as unknown as HTMLElement);
  const busy = h("div", { class: "ed-busy" });
  const stage = h("div", { class: "ed-stage" }, frame, busy);
  const panes = h("div", { class: "ed-panes" });
  const tabs = h("div", { class: "seg ed-tabs" });
  const side = h("div", { class: "ed-side glass-panel" }, tabs, panes);

  const cancelBtn = h("button", { class: "btn", type: "button" }, "Cancel");
  const undoBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Undo" }, iconEl("undo")) as HTMLButtonElement;
  const redoBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Redo" }, iconEl("redo")) as HTMLButtonElement;
  const compareBtn = h("button", { class: "btn", type: "button", title: "Hold to see the original" }, iconEl("compare"), "Compare");
  const autoBtn = h("button", { class: "btn", type: "button" }, iconEl("wand"), "Auto");
  const revertBtn = h("button", { class: "btn", type: "button" }, "Revert to Original");
  const doneBtn = h("button", { class: "btn primary", type: "button" }, "Done");
  const top = h("div", { class: "ed-top" }, cancelBtn, undoBtn, redoBtn, h("span", { class: "head-spacer" }),
    h("span", { class: "ed-title" }, item.name), h("span", { class: "head-spacer" }), compareBtn, autoBtn, revertBtn, doneBtn);
  const root = h("div", { class: "editor" }, top, h("div", { class: "ed-main" }, stage, side));
  document.body.append(root);
  requestAnimationFrame(() => root.classList.add("open"));

  function layout(): void {
    const box = stage.getBoundingClientRect();
    const pad = 24;
    const scale = Math.min((box.width - pad * 2) / natural.w, (box.height - pad * 2) / natural.h);
    frame.style.width = `${Math.max(1, Math.floor(natural.w * scale))}px`;
    frame.style.height = `${Math.max(1, Math.floor(natural.h * scale))}px`;
  }
  const resize = new ResizeObserver(layout);
  resize.observe(stage);

  function stagesFor(): string[] {
    if (tab === "crop") return ["retouch", "geometry", "tone"];
    if (tab === "retouch") return ["retouch", "tone"];
    if (tab === "markup") return ["retouch", "geometry", "tone"];
    return ["retouch", "geometry", "tone", "markup"];
  }

  function previewState(): EditState {
    const p = prune(s);
    if (tab === "crop" && p.geometry) delete p.geometry.crop;
    return p;
  }

  function requestPreview(delay = 50): void {
    window.clearTimeout(timer);
    timer = window.setTimeout(runPreview, delay);
  }

  async function runPreview(): Promise<void> {
    if (inflight) {
      queued = true;
      return;
    }
    inflight = true;
    queued = false;
    const seq = ++previewSeq;
    busy.classList.add("on");
    try {
      const res = await fetch(`/api/media/${item.id}/preview`, {
        method: "POST", headers: { "content-type": "application/json", "x-dam-local": "1" },
        body: JSON.stringify({ state: previewState(), w: Math.min(2048, Math.round(Math.max(stage.clientWidth, stage.clientHeight) * (window.devicePixelRatio || 1))), stages: stagesFor() }),
      });
      if (res.ok && seq === previewSeq) {
        const url = URL.createObjectURL(await res.blob());
        const next = new Image();
        next.src = url;
        await next.decode().catch(() => undefined);
        while (dragging) await new Promise((resolve) => setTimeout(resolve, 50));
        if (seq === previewSeq) {
          natural = { w: next.naturalWidth || 1, h: next.naturalHeight || 1 };
          layout();
          img.src = url;
          if (currentUrl) URL.revokeObjectURL(currentUrl);
          currentUrl = url;
          drawOverlay();
        } else {
          URL.revokeObjectURL(url);
        }
      }
    } finally {
      inflight = false;
      busy.classList.remove("on");
      if (queued) void runPreview();
    }
  }

  function commit(): void {
    undo.push(JSON.stringify(s));
    if (undo.length > 100) undo.shift();
    redo.length = 0;
    syncButtons();
  }

  function syncButtons(): void {
    undoBtn.disabled = undo.length === 0;
    redoBtn.disabled = redo.length === 0;
    revertBtn.classList.toggle("hidden", !item.edit_json && Object.keys(prune(s)).length === 0);
  }

  function group(name: "light" | "color" | "bw" | "detail"): Record<string, number> {
    s[name] = s[name] ?? {};
    return s[name]!;
  }

  const sliderSync: Array<() => void> = [];
  function slider(label: string, min: number, max: number, read: () => number, write: (v: number) => void): HTMLElement {
    const input = h("input", { type: "range", min: String(min), max: String(max), step: "1", class: "ed-range" }) as HTMLInputElement;
    const value = h("span", { class: "ed-val" }, "0");
    const sync = () => {
      const v = Math.round(read() * 100);
      input.value = String(v);
      setText(value, String(v));
      input.classList.toggle("moved", v !== 0);
    };
    let started = false;
    input.addEventListener("pointerdown", () => { if (!started) { commit(); started = true; } });
    input.addEventListener("change", () => { started = false; });
    input.addEventListener("input", () => {
      write(Number(input.value) / 100);
      setText(value, input.value);
      input.classList.toggle("moved", Number(input.value) !== 0);
      requestPreview();
    });
    input.addEventListener("dblclick", () => {
      commit();
      write(0);
      sync();
      requestPreview();
    });
    input.addEventListener("keydown", (event) => event.stopPropagation());
    sliderSync.push(sync);
    sync();
    return h("label", { class: "ed-row" }, h("span", { class: "ed-label" }, label), value, input);
  }

  const adjust = h("div", { class: "ed-pane" });
  if (item.kind === "image" && item.live_video_id) {
    const effect = h("select", { class: "field-input" }, h("option", { value: "" }, "Live (no effect)"), h("option", { value: "long_exposure" }, "Long Exposure")) as HTMLSelectElement;
    effect.addEventListener("change", () => {
      commit();
      (s as Dict).effect = effect.value || undefined;
      requestPreview(0);
    });
    sliderSync.push(() => { effect.value = String((s as Dict).effect ?? ""); });
    adjust.append(h("div", { class: "ed-section" }, h("div", { class: "ed-sec-title" }, "Live Photo Effect"), effect));
  }
  if (item.kind === "image" && (item as Media & { is_raw?: number }).is_raw) {
    const raw = () => { const r = ((s as Dict).raw ?? {}) as Record<string, unknown>; (s as Dict).raw = r; return r; };
    const pick = (label: string, key: string, options: Array<[string, string]>) => {
      const sel = h("select", { class: "field-input" }) as HTMLSelectElement;
      for (const [v, t] of options) sel.append(h("option", { value: v }, t));
      sel.addEventListener("change", () => {
        commit();
        raw()[key] = sel.value;
        if (key === "wb" && sel.value === "kelvin" && raw().temp === undefined) { raw().temp = shot.temp; raw().tint = shot.tint; }
        tempRow.classList.toggle("hidden", raw().wb !== "kelvin"); tintRow.classList.toggle("hidden", raw().wb !== "kelvin"); requestPreview(0); });
      sliderSync.push(() => { sel.value = String(((s as Dict).raw as Record<string, unknown> | undefined)?.[key] ?? options[0][0]); });
      return h("label", { class: "ed-row" }, h("span", { class: "ed-label" }, label), h("span", {}), sel);
    };
    const num = (key: string, fallback: number) => () => Number(((s as Dict).raw as Record<string, unknown> | undefined)?.[key] ?? fallback);
    let shot = { temp: 5500, tint: 0 };
    const wbRow = pick("White Balance", "wb", [["camera", "As Shot"], ["auto", "Auto"], ["daylight", "Daylight"], ["kelvin", "Custom (Kelvin)"]]);
    const tempRow = slider("Temperature (K)", 2000, 12000, () => num("temp", shot.temp)() / 100, (v) => { raw().temp = Math.round(v * 100); });
    const tintRow = slider("Tint", -100, 100, () => num("tint", shot.tint)() / 100, (v) => { raw().tint = Math.round(v * 100); });
    tempRow.classList.add("hidden");
    tintRow.classList.add("hidden");
    sliderSync.push(() => { const k = ((s as Dict).raw as Record<string, unknown> | undefined)?.wb === "kelvin"; tempRow.classList.toggle("hidden", !k); tintRow.classList.toggle("hidden", !k); });
    void api<{ temp: number; tint: number; kelvin: boolean }>(`/media/${item.id}/raw-info`).then((r) => { shot = { temp: r.temp, tint: r.tint }; sliderSync.forEach((f) => f()); });
    adjust.append(h("div", { class: "ed-section" }, h("div", { class: "ed-sec-title" }, "RAW Develop"),
      wbRow, tempRow, tintRow,
      slider("Exposure (stops)", -300, 300, num("exposure", 0), (v) => { raw().exposure = v; }),
      pick("Highlights", "highlights", [["clip", "Clip"], ["blend", "Blend"], ["rebuild", "Recover"]]),
      pick("Demosaic", "demosaic", [["", "Standard (AHD)"], ["quality", "Fine detail (DHT)"], ["fast", "Fast"]]),
      slider("Raw Noise Reduction", 0, 100, num("noise", 0), (v) => { raw().noise = v; }),
      slider("Fringe Red", -100, 100, num("ca_red", 0), (v) => { raw().ca_red = v; }),
      slider("Fringe Blue", -100, 100, num("ca_blue", 0), (v) => { raw().ca_blue = v; })));
  }
  const lens = () => { const l = ((s as Dict).lens ?? {}) as Record<string, number>; (s as Dict).lens = l; return l; };
  adjust.append(h("div", { class: "ed-section" }, h("div", { class: "ed-sec-title" }, "Lens Corrections"),
    slider("Distortion", -100, 100, () => Number(((s as Dict).lens as Record<string, number> | undefined)?.distortion ?? 0), (v) => { lens().distortion = v; }),
    slider("Vignetting", -100, 100, () => Number(((s as Dict).lens as Record<string, number> | undefined)?.vignette ?? 0), (v) => { lens().vignette = v; })));
  for (const sec of SLIDERS) {
    const rows = sec.rows.map(([key, label, min, max]) => slider(label, min, max, () => Number(group(sec.group)[key] ?? 0), (v) => { group(sec.group)[key] = v; }));
    adjust.append(h("div", { class: "ed-section" }, h("div", { class: "ed-sec-title" }, sec.title), ...rows));
  }
  const lv = () => { s.levels = s.levels ?? {}; return s.levels; };
  adjust.append(h("div", { class: "ed-section" }, h("div", { class: "ed-sec-title" }, "Levels"),
    slider("Black", 0, 50, () => Number(lv().black ?? 0), (v) => { lv().black = v; }),
    slider("Midtones", -100, 100, () => Math.log2(Number(lv().gamma ?? 1)), (v) => { lv().gamma = Math.round(2 ** v * 1000) / 1000; }),
    slider("White", -50, 0, () => Number(lv().white ?? 1) - 1, (v) => { lv().white = 1 + v; })));

  const curveSvg = svgEl("svg", { class: "ed-curve", viewBox: "0 0 1 1", preserveAspectRatio: "none" }) as SVGSVGElement;
  const curvePath = svgEl("polyline", { fill: "none", stroke: "currentColor", "stroke-width": 0.012 });
  curveSvg.append(svgEl("line", { x1: 0, y1: 1, x2: 1, y2: 0, stroke: "currentColor", "stroke-width": 0.004, opacity: 0.3 }), curvePath);
  const CURVE_X = [0, 0.25, 0.5, 0.75, 1];
  const dots = CURVE_X.map(() => svgEl("circle", { r: 0.03, class: "ed-dot" }));
  dots.forEach((d) => curveSvg.append(d));
  function curvePoints(): number[][] {
    const pts = s.curves?.rgb;
    return pts && pts.length === 5 ? pts : CURVE_X.map((x) => [x, x]);
  }
  function drawCurve(): void {
    const pts = curvePoints();
    curvePath.setAttribute("points", pts.map(([x, y]) => `${x},${1 - y}`).join(" "));
    pts.forEach(([x, y], i) => { dots[i].setAttribute("cx", String(x)); dots[i].setAttribute("cy", String(1 - y)); });
  }
  dots.forEach((dot, i) => {
    dot.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      commit();
      (dot as unknown as HTMLElement).setPointerCapture((event as PointerEvent).pointerId);
      const move = (ev: PointerEvent) => {
        const box = curveSvg.getBoundingClientRect();
        const y = Math.min(1, Math.max(0, 1 - (ev.clientY - box.top) / box.height));
        const pts = curvePoints().map((p) => [...p]);
        pts[i][1] = Math.round(y * 1000) / 1000;
        s.curves = { rgb: pts };
        drawCurve();
        requestPreview();
      };
      const up = () => { dot.removeEventListener("pointermove", move as EventListener); dot.removeEventListener("pointerup", up); };
      dot.addEventListener("pointermove", move as EventListener);
      dot.addEventListener("pointerup", up);
    });
  });
  const curveReset = h("button", { class: "link-btn", type: "button" }, "Reset");
  curveReset.addEventListener("click", () => { commit(); delete s.curves; drawCurve(); requestPreview(); });
  adjust.append(h("div", { class: "ed-section" }, h("div", { class: "ed-sec-title" }, "Curves", curveReset), curveSvg as unknown as HTMLElement));
  sliderSync.push(drawCurve);

  const filterPane = h("div", { class: "ed-pane hidden" });
  const filterGrid = h("div", { class: "ed-filters" });
  const filterButtons = new Map<string, HTMLElement>();
  for (const [key, label] of FILTERS) {
    const thumb = h("img", { alt: "", draggable: false }) as HTMLImageElement;
    const btn = h("button", { class: "ed-filter", type: "button" }, h("span", { class: "ed-filter-img" }, thumb), h("span", {}, label));
    btn.addEventListener("click", () => {
      commit();
      s.filter = key ? { name: key, amount: s.filter?.amount ?? 1 } : undefined;
      if (!key) delete s.filter;
      syncFilters();
      requestPreview(0);
    });
    filterButtons.set(key, btn);
    filterGrid.append(btn);
    void fetch(`/api/media/${item.id}/preview`, { method: "POST", headers: { "content-type": "application/json", "x-dam-local": "1" }, body: JSON.stringify({ state: key ? { filter: { name: key } } : {}, w: 240, stages: ["tone"] }) })
      .then((r) => (r.ok ? r.blob() : null)).then((b) => { if (b) thumb.src = URL.createObjectURL(b); thumb.addEventListener("load", () => thumb.classList.add("ready"), { once: true }); });
  }
  const amount = slider("Amount", 0, 100, () => (s.filter ? Number(s.filter.amount ?? 1) : 0), (v) => { if (s.filter) s.filter.amount = v; });
  filterPane.append(filterGrid, amount);
  function syncFilters(): void {
    for (const [key, btn] of filterButtons) btn.classList.toggle("active", (s.filter?.name ?? "") === key);
    amount.classList.toggle("hidden", !s.filter);
  }

  const geo = () => { s.geometry = s.geometry ?? {}; return s.geometry; };
  const cropPane = h("div", { class: "ed-pane hidden" });
  const aspectRow = h("div", { class: "chip-list" });
  for (const [label, ratio] of ASPECTS) {
    const chip = h("button", { class: "chip", type: "button" }, label);
    chip.addEventListener("click", () => {
      aspect = ratio === -1 ? natural.w / natural.h : ratio;
      aspectRow.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === chip));
      if (aspect) {
        commit();
        const c = geo().crop ?? { x: 0, y: 0, w: 1, h: 1 };
        const frameRatio = natural.w / natural.h;
        let w = c.w;
        let hgt = (w * frameRatio) / aspect;
        if (hgt > 1) { hgt = 1; w = (aspect * hgt) / frameRatio; }
        geo().crop = { x: Math.min(1 - w, c.x + (c.w - w) / 2), y: Math.min(1 - hgt, Math.max(0, c.y + (c.h - hgt) / 2)), w, h: hgt };
        drawOverlay();
      }
    });
    aspectRow.append(chip);
  }
  const rotateBtn = h("button", { class: "btn", type: "button" }, iconEl("rotate"), "Rotate");
  rotateBtn.addEventListener("click", () => { commit(); geo().rotate = ((geo().rotate ?? 0) + 90) % 360; delete geo().crop; requestPreview(0); });
  const flipHBtn = h("button", { class: "btn", type: "button" }, iconEl("flipH"), "Flip");
  flipHBtn.addEventListener("click", () => { commit(); geo().flipH = !geo().flipH; requestPreview(0); });
  const flipVBtn = h("button", { class: "btn", type: "button" }, iconEl("flipV"), "Flip Vertical");
  flipVBtn.addEventListener("click", () => { commit(); geo().flipV = !geo().flipV; requestPreview(0); });
  const resetCrop = h("button", { class: "btn", type: "button" }, "Reset");
  resetCrop.addEventListener("click", () => { commit(); delete s.geometry; aspect = null; drawOverlay(); requestPreview(0); sliderSync.forEach((f) => f()); });
  cropPane.append(h("div", { class: "ed-section" }, h("div", { class: "ed-sec-title" }, "Aspect"), aspectRow),
    h("div", { class: "row-gap" }, rotateBtn, flipHBtn, flipVBtn, resetCrop),
    slider("Straighten", -45, 45, () => Number(geo().straighten ?? 0) / 100, (v) => { geo().straighten = Math.round(v * 100 * 10) / 10; }));

  const retouchPane = h("div", { class: "ed-pane hidden" });
  const clearSpots = h("button", { class: "btn", type: "button" }, "Clear All");
  clearSpots.addEventListener("click", () => { commit(); delete s.retouch; drawOverlay(); requestPreview(0); });
  const undoSpot = h("button", { class: "btn", type: "button" }, "Remove Last");
  undoSpot.addEventListener("click", () => { if (s.retouch?.length) { commit(); s.retouch.pop(); if (!s.retouch.length) delete s.retouch; drawOverlay(); requestPreview(0); } });
  const cleanupHint = h("p", { class: "field-hint" }, "Click a blemish, or brush over a person, wire or object to remove it. Brush over a face to pixelate it. The fill comes from the surrounding pixels.");
  const modeRow = h("div", { class: "seg" });
  const brushMode = h("button", { type: "button", class: "active" }, "Brush") as HTMLButtonElement;
  const selectMode = h("button", { type: "button", disabled: true, title: "Click an object to select and remove it" }, "Select Object") as HTMLButtonElement;
  for (const [btn, mode] of [[brushMode, "brush"], [selectMode, "select"]] as const) {
    btn.addEventListener("click", () => { cleanMode = mode; brushMode.classList.toggle("active", mode === "brush"); selectMode.classList.toggle("active", mode === "select"); });
  }
  modeRow.append(brushMode, selectMode);
  const suggestLabel = h("span", {}, "Show Distractions");
  const suggestBtn = h("button", { class: "btn", type: "button", disabled: true }, iconEl("wand"), suggestLabel) as HTMLButtonElement;
  suggestBtn.addEventListener("click", () => {
    if (suggestions.length) { suggestions = []; setText(suggestLabel, "Show Distractions"); setText(cleanStatus, ""); drawOverlay(); return; }
    suggestBtn.disabled = true;
    setText(cleanStatus, "Looking for distractions...");
    api<{ objects: Suggestion[] }>(`/media/${item.id}/cleanup/suggest`).then((res) => {
      suggestions = res.objects;
      setText(cleanStatus, suggestions.length ? `${suggestions.length} found. Click an outline to remove it.` : "Nothing to suggest in this photo.");
      if (suggestions.length) setText(suggestLabel, "Hide Distractions");
      drawOverlay();
    }).catch((err) => setText(cleanStatus, (err as { detail?: string }).detail ?? (err as Error).message))
      .finally(() => { suggestBtn.disabled = false; });
  });
  const cleanStatus = h("p", { class: "field-hint ed-clean-status" }, "");
  retouchPane.append(cleanupHint, modeRow, suggestBtn, cleanStatus,
    slider("Brush Size", 50, 800, () => brush * 100 * 100 / 100, (v) => { brush = v / 100; }), h("div", { class: "row-gap" }, undoSpot, clearSpots));

  function loadCleanInfo(): void {
    if (cleanInfo) return;
    cleanInfo = { fill: false, segment: false, suggest: false, faces: false, faces_found: [] };
    api<CleanInfo>(`/media/${item.id}/cleanup`).then((res) => {
      cleanInfo = res;
      selectMode.disabled = !res.segment;
      suggestBtn.disabled = !res.suggest;
      if (!res.segment && !res.suggest) setText(cleanStatus, "Object selection models are not installed. The brush still works.");
    }).catch(() => { cleanInfo = null; });
  }

  function segmentWith(body: Dict, shown: Box4, used?: Suggestion): void {
    if (pendingBox) return;
    pendingBox = shown;
    setText(cleanStatus, "Selecting...");
    drawOverlay();
    api<{ polygons: Array<Array<[number, number]>> }>(`/media/${item.id}/cleanup/segment`, { method: "POST", body: JSON.stringify(body) }).then((res) => {
      pendingBox = null;
      if (!res.polygons.length) { setText(cleanStatus, "Nothing selectable there. Try brushing over it."); drawOverlay(); return; }
      commit();
      s.retouch = [...(s.retouch ?? []), { kind: "mask", polygons: res.polygons, ...(used ? { label: used.label } : {}) }];
      if (used) suggestions = suggestions.filter((sg) => sg !== used);
      setText(cleanStatus, "");
      drawOverlay();
      requestPreview(0);
    }).catch((err) => {
      pendingBox = null;
      setText(cleanStatus, (err as { detail?: string }).detail ?? (err as Error).message);
      drawOverlay();
    });
  }

  function faceUnder(points: Array<[number, number]>): Box4 | null {
    for (const f of cleanInfo?.faces_found ?? []) {
      const inside = points.filter(([x, y]) => x >= f[0] && x <= f[0] + f[2] && y >= f[1] && y <= f[1] + f[3]).length;
      if (inside >= Math.max(1, points.length * 0.4)) return f;
    }
    return null;
  }

  const markupPane = h("div", { class: "ed-pane hidden" });
  const toolRow = h("div", { class: "seg" });
  const TOOLS: Array<[string, string, IconName]> = [["pen", "Pen", "pen"], ["rect", "Box", "shape"], ["ellipse", "Oval", "dot"], ["arrow", "Arrow", "cursor"], ["text", "Text", "type"]];
  for (const [key, label] of TOOLS) {
    const btn = h("button", { type: "button", class: key === tool ? "active" : "" }, label);
    btn.addEventListener("click", () => { tool = key; toolRow.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn)); });
    toolRow.append(btn);
  }
  const swatches = h("div", { class: "ed-swatches" });
  for (const c of COLORS) {
    const sw = h("button", { class: `ed-swatch${c === color ? " active" : ""}`, type: "button", style: `background:${c}`, "aria-label": c });
    sw.addEventListener("click", () => { color = c; swatches.querySelectorAll(".ed-swatch").forEach((x) => x.classList.toggle("active", x === sw)); });
    swatches.append(sw);
  }
  const undoShape = h("button", { class: "btn", type: "button" }, "Remove Last");
  undoShape.addEventListener("click", () => { if (s.markup?.length) { commit(); s.markup.pop(); drawOverlay(); } });
  markupPane.append(toolRow, swatches, slider("Line Width", 10, 300, () => penWidth * 100 * 100 / 100 * 1, (v) => { penWidth = v / 100; }), undoShape);

  const PANES: Record<Tab, HTMLElement> = { adjust, filters: filterPane, crop: cropPane, retouch: retouchPane, markup: markupPane };
  panes.append(...Object.values(PANES));
  for (const [key, label] of [["adjust", "Adjust"], ["filters", "Filters"], ["crop", "Crop"], ["retouch", "Clean Up"], ["markup", "Markup"]] as const) {
    const btn = h("button", { type: "button", class: key === tab ? "active" : "" }, label);
    btn.addEventListener("click", () => {
      tab = key;
      tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
      for (const [k, pane] of Object.entries(PANES)) pane.classList.toggle("hidden", k !== key);
      overlay.classList.toggle("interactive", key === "crop" || key === "retouch" || key === "markup");
      if (key === "retouch") loadCleanInfo();
      drawOverlay();
      requestPreview(0);
    });
    tabs.append(btn);
  }

  function drawOverlay(): void {
    const nodes: SVGElement[] = [];
    if (tab === "crop") {
      const c = s.geometry?.crop ?? { x: 0, y: 0, w: 1, h: 1 };
      const shade = svgEl("path", { class: "ed-shade", d: `M0 0H1V1H0Z M${c.x} ${c.y}V${c.y + c.h}H${c.x + c.w}V${c.y}Z`, "fill-rule": "evenodd" });
      const rect = svgEl("rect", { class: "ed-crop", x: c.x, y: c.y, width: c.w, height: c.h, "data-h": "move" });
      nodes.push(shade, rect);
      for (const third of [1 / 3, 2 / 3]) {
        nodes.push(svgEl("line", { class: "ed-grid", x1: c.x + c.w * third, y1: c.y, x2: c.x + c.w * third, y2: c.y + c.h }));
        nodes.push(svgEl("line", { class: "ed-grid", x1: c.x, y1: c.y + c.h * third, x2: c.x + c.w, y2: c.y + c.h * third }));
      }
      const hx0 = 14 / Math.max(1, frame.clientWidth);
      const hy0 = 14 / Math.max(1, frame.clientHeight);
      for (const [hx, hy, key] of [[c.x, c.y, "nw"], [c.x + c.w, c.y, "ne"], [c.x, c.y + c.h, "sw"], [c.x + c.w, c.y + c.h, "se"]] as Array<[number, number, string]>) {
        nodes.push(svgEl("rect", { class: "ed-handle", x: hx - hx0 / 2, y: hy - hy0 / 2, width: hx0, height: hy0, "data-h": key }));
      }
    } else if (tab === "retouch") {
      const short = Math.min(natural.w, natural.h);
      for (const spot of s.retouch ?? []) {
        if (spot.kind === "mask") {
          nodes.push(svgEl("path", { class: "ed-mask", "fill-rule": "evenodd", d: (spot.polygons ?? []).map((poly) => `M${poly.map(([x, y]) => `${x} ${y}`).join("L")}Z`).join(" ") }));
        } else if (spot.kind === "pixelate" && spot.box) {
          nodes.push(svgEl("rect", { class: "ed-pixel", x: spot.box[0], y: spot.box[1], width: spot.box[2], height: spot.box[3] }));
        } else {
          const r = spot.r ?? 0.02;
          nodes.push(spot.points && spot.points.length > 1 ? strokeNode(spot) : svgEl("ellipse", { class: "ed-spot", cx: spot.x ?? 0, cy: spot.y ?? 0, rx: (r * short) / natural.w, ry: (r * short) / natural.h }));
        }
      }
      suggestions.forEach((sg, i) => {
        const rect = svgEl("rect", { class: "ed-suggest", x: sg.box[0], y: sg.box[1], width: sg.box[2], height: sg.box[3], "data-sug": i });
        const title = svgEl("title", {});
        title.textContent = `Remove ${sg.label}`;
        rect.append(title);
        nodes.push(rect);
      });
      if (pendingBox) nodes.push(svgEl("rect", { class: "ed-pending", x: pendingBox[0], y: pendingBox[1], width: pendingBox[2], height: pendingBox[3] }));
    } else if (tab === "markup") {
      for (const shape of s.markup ?? []) nodes.push(shapeNode(shape));
    }
    overlay.replaceChildren(...nodes);
  }

  function strokeNode(spot: NonNullable<EditState["retouch"]>[number]): SVGElement {
    const short = Math.min(natural.w, natural.h);
    const sw = ((spot.r ?? 0.02) * 2 * short) / Math.max(natural.w, natural.h);
    return svgEl("polyline", { class: "ed-stroke", "stroke-width": sw, fill: "none", "stroke-linecap": "round", "stroke-linejoin": "round", points: (spot.points ?? []).map(([x, y]) => `${x},${y}`).join(" ") });
  }

  function shapeNode(shape: NonNullable<EditState["markup"]>[number]): SVGElement {
    const short = Math.min(natural.w, natural.h);
    const sw = (shape.width * short) / Math.max(natural.w, natural.h);
    const common = { stroke: shape.color, "stroke-width": sw, fill: "none", "vector-effect": "none", "stroke-linecap": "round", "stroke-linejoin": "round" };
    const p = shape.points;
    if (shape.type === "pen") return svgEl("polyline", { ...common, points: p.map(([x, y]) => `${x},${y}`).join(" ") });
    if (shape.type === "rect" && p.length === 2) return svgEl("rect", { ...common, x: Math.min(p[0][0], p[1][0]), y: Math.min(p[0][1], p[1][1]), width: Math.abs(p[1][0] - p[0][0]), height: Math.abs(p[1][1] - p[0][1]) });
    if (shape.type === "ellipse" && p.length === 2) return svgEl("ellipse", { ...common, cx: (p[0][0] + p[1][0]) / 2, cy: (p[0][1] + p[1][1]) / 2, rx: Math.abs(p[1][0] - p[0][0]) / 2, ry: Math.abs(p[1][1] - p[0][1]) / 2 });
    if (shape.type === "arrow" && p.length === 2) {
      const g = svgEl("g", {});
      const [x0, y0] = [p[0][0] * natural.w, p[0][1] * natural.h];
      const [x1, y1] = [p[1][0] * natural.w, p[1][1] * natural.h];
      const ang = Math.atan2(y1 - y0, x1 - x0);
      const head = shape.width * short * 4;
      g.append(svgEl("line", { ...common, x1: p[0][0], y1: p[0][1], x2: p[1][0], y2: p[1][1] }));
      for (const side of [-0.45, 0.45]) {
        if (!Number.isFinite(head) || !Number.isFinite(ang) || (x0 === x1 && y0 === y1)) break;
        g.append(svgEl("line", { ...common, x1: p[1][0], y1: p[1][1], x2: (x1 - head * Math.cos(ang + side)) / natural.w, y2: (y1 - head * Math.sin(ang + side)) / natural.h }));
      }
      return g;
    }
    const text = svgEl("text", { x: p[0]?.[0] ?? 0, y: (p[0]?.[1] ?? 0) + (shape.size ?? 0.05) * short / natural.h, fill: shape.color, "font-size": ((shape.size ?? 0.05) * short) / natural.h, class: "ed-text" });
    text.textContent = shape.text ?? "";
    return text;
  }

  function pointFrom(event: PointerEvent): [number, number] {
    const box = overlay.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)), Math.min(1, Math.max(0, (event.clientY - box.top) / box.height))];
  }

  overlay.addEventListener("pointerdown", (event) => {
    if (tab !== "crop" && tab !== "retouch" && tab !== "markup") return;
    event.preventDefault();
    overlay.setPointerCapture(event.pointerId);
    dragging = true;
    const release = () => { dragging = false; overlay.removeEventListener("pointerup", release); overlay.removeEventListener("pointercancel", release); };
    overlay.addEventListener("pointerup", release);
    overlay.addEventListener("pointercancel", release);
    const start = pointFrom(event);
    if (tab === "retouch") {
      const sugIndex = (event.target as Element).getAttribute("data-sug");
      const picked = sugIndex !== null ? suggestions[Number(sugIndex)] : undefined;
      if (picked) { segmentWith({ box: picked.box }, picked.box, picked); return; }
      if (cleanMode === "select") {
        const d = 0.04;
        segmentWith({ x: start[0], y: start[1] }, [Math.max(0, start[0] - d / 2), Math.max(0, start[1] - d / 2), d, d]);
        return;
      }
      commit();
      const round = (p: [number, number]): [number, number] => [Math.round(p[0] * 1e4) / 1e4, Math.round(p[1] * 1e4) / 1e4];
      const spot = { x: round(start)[0], y: round(start)[1], r: brush, points: [round(start)] };
      s.retouch = [...(s.retouch ?? []), spot];
      drawOverlay();
      const line = strokeNode(spot);
      overlay.append(line);
      const move = (ev: PointerEvent) => {
        const pt = round(pointFrom(ev));
        const last = spot.points[spot.points.length - 1];
        if (Math.hypot(pt[0] - last[0], pt[1] - last[1]) < 0.003 || spot.points.length >= 1500) return;
        spot.points.push(pt);
        line.setAttribute("points", spot.points.map(([x, y]) => `${x},${y}`).join(" "));
      };
      const up = () => {
        overlay.removeEventListener("pointermove", move);
        overlay.removeEventListener("pointerup", up);
        const face = spot.points.length >= 3 ? faceUnder(spot.points) : null;
        if (face && s.retouch) s.retouch[s.retouch.length - 1] = { kind: "pixelate", box: face };
        else if (spot.points.length < 3) delete (spot as { points?: unknown }).points;
        drawOverlay();
        requestPreview(0);
      };
      overlay.addEventListener("pointermove", move);
      overlay.addEventListener("pointerup", up);
      return;
    }
    if (tab === "markup") {
      if (tool === "text") {
        void promptText("Add Text", "", "", "Add").then((text) => {
          if (!text) return;
          commit();
          s.markup = [...(s.markup ?? []), { type: "text", points: [start], color, width: penWidth, text, size: 0.05 }];
          drawOverlay();
        });
        return;
      }
      commit();
      const shape = { type: tool, points: [start, start], color, width: penWidth };
      if (tool === "pen") shape.points = [start];
      s.markup = [...(s.markup ?? []), shape];
      let node = shapeNode(shape);
      overlay.append(node);
      const move = (ev: PointerEvent) => {
        const pt = pointFrom(ev);
        if (tool === "pen") shape.points.push(pt);
        else shape.points[1] = pt;
        const next = shapeNode(shape);
        node.replaceWith(next);
        node = next;
      };
      const up = () => { overlay.removeEventListener("pointermove", move); overlay.removeEventListener("pointerup", up); };
      overlay.addEventListener("pointermove", move);
      overlay.addEventListener("pointerup", up);
      return;
    }
    const handle = (event.target as Element).getAttribute("data-h") ?? "new";
    commit();
    const c0 = { ...(s.geometry?.crop ?? { x: 0, y: 0, w: 1, h: 1 }) };
    const frameRatio = natural.w / natural.h;
    const move = (ev: PointerEvent) => {
      const [px, py] = pointFrom(ev);
      let { x, y, w, h: hh } = c0;
      if (handle === "move") {
        x = Math.min(1 - w, Math.max(0, c0.x + px - start[0]));
        y = Math.min(1 - hh, Math.max(0, c0.y + py - start[1]));
      } else {
        const ax = handle.includes("w") ? c0.x + c0.w : handle === "new" ? start[0] : c0.x;
        const ay = handle.includes("n") ? c0.y + c0.h : handle === "new" ? start[1] : c0.y;
        x = Math.min(ax, px);
        y = Math.min(ay, py);
        w = Math.max(0.03, Math.abs(px - ax));
        hh = Math.max(0.03, Math.abs(py - ay));
        if (aspect) {
          hh = (w * frameRatio) / aspect;
          if (py < ay) y = ay - hh;
          if (y < 0 || y + hh > 1) {
            hh = Math.min(hh, py < ay ? ay : 1 - ay);
            w = (hh * aspect) / frameRatio;
            if (px < ax) x = ax - w;
            if (py < ay) y = ay - hh;
          }
        }
      }
      geo().crop = { x: Math.max(0, x), y: Math.max(0, y), w: Math.min(1, w), h: Math.min(1, hh) };
      drawOverlay();
    };
    const up = () => { overlay.removeEventListener("pointermove", move); overlay.removeEventListener("pointerup", up); };
    overlay.addEventListener("pointermove", move);
    overlay.addEventListener("pointerup", up);
  });

  function restore(raw: string): void {
    s = JSON.parse(raw) as EditState;
    sliderSync.forEach((f) => f());
    syncFilters();
    drawOverlay();
    requestPreview(0);
    syncButtons();
  }
  undoBtn.addEventListener("click", () => { const prev = undo.pop(); if (prev === undefined) return; redo.push(JSON.stringify(s)); restore(prev); });
  redoBtn.addEventListener("click", () => { const next = redo.pop(); if (next === undefined) return; undo.push(JSON.stringify(s)); restore(next); });
  autoBtn.addEventListener("click", async () => {
    const res = await api<{ state: EditState }>(`/media/${item.id}/auto`);
    commit();
    s.light = { ...(s.light ?? {}), ...(res.state.light ?? {}) };
    s.color = { ...(s.color ?? {}), ...(res.state.color ?? {}) };
    sliderSync.forEach((f) => f());
    requestPreview(0);
  });
  revertBtn.addEventListener("click", async () => {
    commit();
    s = {};
    sliderSync.forEach((f) => f());
    syncFilters();
    drawOverlay();
    requestPreview(0);
  });
  let comparing = false;
  let shown = "";
  const startCompare = () => {
    if (comparing) return;
    comparing = true;
    shown = img.src;
    void fetch(`/api/media/${item.id}/preview`, { method: "POST", headers: { "content-type": "application/json", "x-dam-local": "1" }, body: JSON.stringify({ state: {}, w: 1600 }) })
      .then((r) => r.blob()).then((b) => {
        if (!comparing) return;
        const url = URL.createObjectURL(b);
        const probe = new Image();
        probe.src = url;
        void probe.decode().then(() => {
          if (!comparing) return;
          natural = { w: probe.naturalWidth, h: probe.naturalHeight };
          layout();
          img.src = url;
        });
      });
  };
  const endCompare = () => {
    if (!comparing) return;
    comparing = false;
    img.src = shown;
    requestPreview(0);
  };
  compareBtn.addEventListener("pointerdown", startCompare);
  compareBtn.addEventListener("pointerup", endCompare);
  compareBtn.addEventListener("pointerleave", endCompare);

  function close(): void {
    open = false;
    resize.disconnect();
    window.removeEventListener("keydown", keys, true);
    window.removeEventListener("keyup", keyUp);
    root.classList.remove("open");
    setTimeout(() => {
      root.remove();
      if (currentUrl) URL.revokeObjectURL(currentUrl);
    }, 180);
  }
  cancelBtn.addEventListener("click", close);
  doneBtn.addEventListener("click", async () => {
    doneBtn.setAttribute("disabled", "");
    try {
      await saveState(item, s);
      toast("Edits saved");
      close();
    } catch (err) {
      doneBtn.removeAttribute("disabled");
      toast(String((err as Error).message), "error");
    }
  });
  const keys = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null;
    if (target && target.closest("input:not([type=range]), textarea, .modal-backdrop")) return;
    event.stopPropagation();
    if (event.key === "Escape") { event.preventDefault(); close(); }
    else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); (event.shiftKey ? redoBtn : undoBtn).click(); }
    else if (event.key === "Enter" && !event.metaKey) { event.preventDefault(); doneBtn.click(); }
    else if (event.key === "m") { startCompare(); }
  };
  const keyUp = (event: KeyboardEvent) => { if (event.key === "m") endCompare(); };
  window.addEventListener("keydown", keys, true);
  window.addEventListener("keyup", keyUp);

  void api<{ state: EditState }>(`/media/${item.id}/edits`).then((res) => {
    s = res.state ?? {};
    sliderSync.forEach((f) => f());
    syncFilters();
    syncButtons();
    requestPreview(0);
  });
  img.addEventListener("load", () => {
    if (!currentUrl) {
      natural = { w: img.naturalWidth || 1, h: img.naturalHeight || 1 };
      layout();
    }
  }, { once: true });
}

function openTrim(item: Media): void {
  open = true;
  const video = h("video", { src: `/api/media/${item.id}/file`, controls: true, playsinline: true, class: "trim-video" }) as HTMLVideoElement;
  const inRange = h("input", { type: "range", min: "0", max: "1000", value: "0", class: "ed-range" }) as HTMLInputElement;
  const outRange = h("input", { type: "range", min: "0", max: "1000", value: "1000", class: "ed-range" }) as HTMLInputElement;
  const inVal = h("span", { class: "ed-val" }, "0:00");
  const outVal = h("span", { class: "ed-val" }, "0:00");
  let duration = item.duration ?? 0;
  const t = (r: HTMLInputElement) => (Number(r.value) / 1000) * duration;
  const sync = () => {
    setText(inVal, formatDuration(t(inRange)));
    setText(outVal, formatDuration(t(outRange)));
  };
  video.addEventListener("loadedmetadata", () => {
    duration = video.duration || duration;
    if (item.trim_in) inRange.value = String(Math.round((item.trim_in / duration) * 1000));
    if (item.trim_out) outRange.value = String(Math.round((item.trim_out / duration) * 1000));
    sync();
  });
  for (const [r, isIn] of [[inRange, true], [outRange, false]] as const) {
    r.addEventListener("input", () => {
      if (Number(inRange.value) >= Number(outRange.value) - 5) r.value = isIn ? String(Number(outRange.value) - 5) : String(Number(inRange.value) + 5);
      video.currentTime = t(r);
      sync();
    });
  }
  const cancel = h("button", { class: "btn", type: "button" }, "Cancel");
  const reset = h("button", { class: "btn", type: "button" }, "Reset Trim");
  const asNew = h("button", { class: "btn", type: "button" }, "Save as New Clip");
  const done = h("button", { class: "btn primary", type: "button" }, "Done");
  const root = h("div", { class: "editor" },
    h("div", { class: "ed-top" }, cancel, h("span", { class: "head-spacer" }), h("span", { class: "ed-title" }, `Trim ${item.name}`), h("span", { class: "head-spacer" }), reset, asNew, done),
    h("div", { class: "trim-main" }, video,
      h("div", { class: "trim-rows glass-panel" }, h("label", { class: "ed-row" }, h("span", { class: "ed-label" }, "Start"), inVal, inRange),
        h("label", { class: "ed-row" }, h("span", { class: "ed-label" }, "End"), outVal, outRange))));
  document.body.append(root);
  requestAnimationFrame(() => root.classList.add("open"));
  const escape = (event: KeyboardEvent) => {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    event.preventDefault();
    close();
  };
  window.addEventListener("keydown", escape, true);
  const close = () => {
    open = false;
    window.removeEventListener("keydown", escape, true);
    root.classList.remove("open");
    setTimeout(() => root.remove(), 180);
  };
  const save = async (): Promise<boolean> => {
    const tin = t(inRange);
    const tout = t(outRange);
    const body = { trim_in: tin > 0.05 ? tin : null, trim_out: tout < duration - 0.05 ? tout : null };
    await api(`/media/${item.id}/trim`, { method: "POST", body: JSON.stringify(body) });
    patchMedia([item.id], body as Partial<Media>);
    return Boolean(body.trim_in || body.trim_out);
  };
  cancel.addEventListener("click", close);
  reset.addEventListener("click", () => { inRange.value = "0"; outRange.value = "1000"; sync(); });
  done.addEventListener("click", async () => { await save(); toast("Trim saved"); close(); });
  asNew.addEventListener("click", async () => {
    if (!(await save())) { toast("Move the start or end first"); return; }
    try {
      await api<{ id: number }>(`/media/${item.id}/trim/export`, { method: "POST" });
      toast("Saved the trimmed clip as a new item");
      close();
    } catch (err) {
      toast(String((err as Error).message), "error");
    }
  });
}

function honorTrim(video: HTMLVideoElement, id: number): void {
  const item = store.byId.get(id);
  if (!item || (!item.trim_in && !item.trim_out)) return;
  video.addEventListener("loadedmetadata", () => { if (item.trim_in) video.currentTime = item.trim_in; }, { once: true });
  video.addEventListener("timeupdate", () => {
    if (item.trim_out && video.currentTime >= item.trim_out) {
      video.pause();
      video.currentTime = item.trim_in ?? 0;
    }
  });
}

function editEntries(item: Media): CtxEntry[] {
  const ids = store.selection.has(item.id) && store.selection.size > 1 ? [...store.selection] : [item.id];
  const entries: CtxEntry[] = [{ label: item.kind === "video" ? "Trim..." : "Edit...", icon: item.kind === "video" ? "scissors" : "sliders", action: () => openEditor(item) }];
  if (item.kind === "image") {
    if (item.edit_json) entries.push({ label: "Copy Edits", icon: "copy", action: () => void copyEdits(item.id) });
    if (clipboard) entries.push({ label: "Paste Edits", icon: "copy", action: () => void pasteEdits(ids) });
    if (item.edit_json) entries.push({ label: "Revert to Original", icon: "reset", action: () => void revertToOriginal(ids) });
  }
  return entries;
}

let registered = false;

export function registerEditor(): void {
  if (registered) return;
  registered = true;
  viewerHooks.toolbar.push((current) => {
    const btn = h("button", { class: "btn viewer-edit", type: "button" }, "Edit");
    btn.addEventListener("click", () => {
      const id = current();
      const item = id === null ? undefined : store.byId.get(id);
      if (item) openEditor(item);
    });
    return btn;
  });
  viewerHooks.keys.push((event, id) => {
    if (event.key !== "e" || event.metaKey || event.ctrlKey || open) return false;
    const target = event.target as HTMLElement | null;
    if (target && target.closest("input, textarea, select")) return false;
    const item = store.byId.get(id);
    if (!item) return false;
    event.preventDefault();
    openEditor(item);
    return true;
  });
  viewerHooks.videoReady = honorTrim;
  tileHooks.ctx.push(editEntries);
  selectbarExtras.push({ label: "Paste Edits", icon: "copy", handler: (ids) => { if (clipboard) void pasteEdits(ids); else toast("Copy edits from an edited photo first"); } });
  window.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey) || !event.shiftKey || open) return;
    const key = event.key.toLowerCase();
    const viewerId = store.viewer ? store.viewer.ids[store.viewer.index] : null;
    const ids = viewerId !== null && viewerId !== undefined ? [viewerId] : [...store.selection];
    if (!ids.length) return;
    if (key === "c") { event.preventDefault(); void copyEdits(ids[0]); }
    else if (key === "v") { event.preventDefault(); void pasteEdits(ids); }
  });
}
