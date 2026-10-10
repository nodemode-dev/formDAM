import { api, thumbUrl } from "../../engine/api.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";

export type MapPoint = [number, number, number];

interface Country {
  iso: string;
  name: string;
  rings: number[][][];
}

export interface MapView {
  el: HTMLElement;
  setPoints(points: MapPoint[]): void;
  fit(points?: MapPoint[]): void;
  center(lat: number, lon: number, zoom?: number): void;
  setPin(lat: number | null, lon: number | null): void;
  bounds(): [number, number, number, number];
  destroy(): void;
}

export interface MapOptions {
  onOpen?: (ids: number[]) => void;
  onPick?: (lat: number, lon: number) => void;
  onMove?: () => void;
  markers?: boolean;
}

const TILE = 256;
const CELL = 58;
const THUMB = 46;
const MAX_ZOOM = 17;

let worldCache: Promise<Array<{ name: string; rings: Float64Array[] }>> | null = null;

function project(lat: number, lon: number): [number, number] {
  const clamped = Math.max(-85.05, Math.min(85.05, lat));
  const s = Math.sin((clamped * Math.PI) / 180);
  return [(lon + 180) / 360, 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)];
}

function unproject(x: number, y: number): [number, number] {
  const lon = x * 360 - 180;
  const n = Math.PI - 2 * Math.PI * y;
  return [(180 / Math.PI) * Math.atan(Math.sinh(n)), lon];
}

function world(): Promise<Array<{ name: string; rings: Float64Array[] }>> {
  if (!worldCache) {
    worldCache = api<{ countries: Country[] }>("/places/countries").then((res) => res.countries.map((c) => ({
      name: c.name,
      rings: c.rings.map((ring) => {
        const out = new Float64Array(ring.length * 2);
        ring.forEach((p, i) => {
          const [x, y] = project(p[1], p[0]);
          out[i * 2] = x;
          out[i * 2 + 1] = y;
        });
        return out;
      }),
    })));
  }
  return worldCache;
}

const thumbs = new Map<number, HTMLImageElement>();

export function createMap(opts: MapOptions = {}): MapView {
  const canvas = h("canvas", { class: "map-canvas" }) as HTMLCanvasElement;
  const zoomIn = h("button", { class: "icon-btn map-btn", type: "button", "aria-label": "Zoom in" }, iconEl("plus"));
  const zoomOut = h("button", { class: "icon-btn map-btn", type: "button", "aria-label": "Zoom out" }, iconEl("minus"));
  const probe = h("span", { class: "map-probe" });
  const el = h("div", { class: "map-view" }, canvas, h("div", { class: "map-controls" }, zoomIn, zoomOut), probe);
  const ctx = canvas.getContext("2d")!;
  let land: Array<{ name: string; rings: Float64Array[] }> = [];
  let points: MapPoint[] = [];
  let projected = new Float64Array(0);
  let cx = 0.5;
  let cy = 0.42;
  let zoom = 1;
  let width = 0;
  let height = 0;
  let dpr = 1;
  let frame = 0;
  let alive = true;
  let pin: [number, number] | null = null;
  let hits: Array<{ x: number; y: number; ids: number[]; bx: [number, number, number, number] }> = [];

  const scale = () => TILE * 2 ** zoom;
  const minZoom = () => Math.max(0, Math.log2(Math.max(1, width) / TILE));

  function clampView(): void {
    zoom = Math.min(MAX_ZOOM, Math.max(minZoom(), zoom));
    const halfY = height / 2 / scale();
    cy = halfY >= 0.5 ? 0.5 : Math.min(1 - halfY, Math.max(halfY, cy));
    cx = ((cx % 1) + 1) % 1;
  }

  function toScreen(x: number, y: number): [number, number] {
    let dx = x - cx;
    if (dx > 0.5) dx -= 1;
    if (dx < -0.5) dx += 1;
    return [width / 2 + dx * scale(), height / 2 + (y - cy) * scale()];
  }

  function fromScreen(sx: number, sy: number): [number, number] {
    return [cx + (sx - width / 2) / scale(), cy + (sy - height / 2) / scale()];
  }

  function colors(): { line: string; accent: string; text: string } {
    const style = getComputedStyle(el);
    return { line: style.color, accent: getComputedStyle(probe).color, text: style.getPropertyValue("--map-ink").trim() || "#fff" };
  }

  function draw(): void {
    frame = 0;
    if (!alive || width === 0) return;
    const c = colors();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const s = scale();
    const copies = Math.ceil(width / s / 2) + 1;
    ctx.lineJoin = "round";
    for (let k = -copies; k <= copies; k++) {
      const ox = width / 2 + (k - cx) * s;
      const oy = height / 2 - cy * s;
      if (ox + s < 0 || ox > width) continue;
      ctx.beginPath();
      for (const country of land) {
        for (const ring of country.rings) {
          for (let i = 0; i < ring.length; i += 2) {
            const x = ox + ring[i] * s;
            const y = oy + ring[i + 1] * s;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.closePath();
        }
      }
      ctx.globalAlpha = 0.14;
      ctx.fillStyle = c.line;
      ctx.fill("evenodd");
      ctx.globalAlpha = 0.45;
      ctx.lineWidth = 0.8;
      ctx.strokeStyle = c.line;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    hits = [];
    if (opts.markers !== false && points.length) drawClusters(c);
    if (pin) {
      const [px, py] = toScreen(...project(pin[0], pin[1]));
      ctx.fillStyle = c.accent;
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(px, py - 14, 8, Math.PI * 0.85, Math.PI * 2.15);
      ctx.lineTo(px, py);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.fillStyle = "#fff";
      ctx.arc(px, py - 14, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawClusters(c: { accent: string }): void {
    const cells = new Map<string, { sx: number; sy: number; ids: number[]; bx: [number, number, number, number] }>();
    for (let i = 0; i < points.length; i++) {
      const [sx, sy] = toScreen(projected[i * 2], projected[i * 2 + 1]);
      if (sx < -CELL || sy < -CELL || sx > width + CELL || sy > height + CELL) continue;
      const key = `${Math.floor(sx / CELL)}:${Math.floor(sy / CELL)}`;
      const lat = points[i][1];
      const lon = points[i][2];
      const cell = cells.get(key);
      if (cell) {
        cell.ids.push(points[i][0]);
        cell.bx = [Math.min(cell.bx[0], lat), Math.min(cell.bx[1], lon), Math.max(cell.bx[2], lat), Math.max(cell.bx[3], lon)];
      } else {
        cells.set(key, { sx, sy, ids: [points[i][0]], bx: [lat, lon, lat, lon] });
      }
    }
    for (const cell of cells.values()) {
      const x = Math.round(cell.sx - THUMB / 2);
      const y = Math.round(cell.sy - THUMB / 2);
      ctx.save();
      ctx.shadowColor = "rgba(0,0,0,0.45)";
      ctx.shadowBlur = 8;
      ctx.fillStyle = "#fff";
      roundRect(x - 2, y - 2, THUMB + 4, THUMB + 4, 9);
      ctx.fill();
      ctx.restore();
      const img = thumbFor(cell.ids[0]);
      ctx.save();
      roundRect(x, y, THUMB, THUMB, 7);
      ctx.clip();
      if (img.complete && img.naturalWidth) {
        const side = Math.min(img.naturalWidth, img.naturalHeight);
        ctx.drawImage(img, (img.naturalWidth - side) / 2, (img.naturalHeight - side) / 2, side, side, x, y, THUMB, THUMB);
      } else {
        ctx.fillStyle = "#555";
        ctx.fillRect(x, y, THUMB, THUMB);
      }
      ctx.restore();
      if (cell.ids.length > 1) {
        const label = cell.ids.length > 999 ? `${Math.round(cell.ids.length / 100) / 10}k` : String(cell.ids.length);
        ctx.font = "600 11px system-ui, sans-serif";
        const w = Math.max(18, ctx.measureText(label).width + 10);
        ctx.fillStyle = c.accent;
        roundRect(x + THUMB - w + 6, y - 8, w, 18, 9);
        ctx.fill();
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(label, x + THUMB - w / 2 + 6, y + 1);
      }
      hits.push({ x: cell.sx, y: cell.sy, ids: cell.ids, bx: cell.bx });
    }
  }

  function roundRect(x: number, y: number, w: number, hgt: number, r: number): void {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + hgt, r);
    ctx.arcTo(x + w, y + hgt, x, y + hgt, r);
    ctx.arcTo(x, y + hgt, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function thumbFor(id: number): HTMLImageElement {
    let img = thumbs.get(id);
    if (!img) {
      img = new Image();
      img.decoding = "async";
      img.addEventListener("load", schedule, { once: true });
      img.src = thumbUrl(id, 384);
      thumbs.set(id, img);
    } else if (!img.complete) {
      img.addEventListener("load", schedule, { once: true });
    }
    return img;
  }

  function schedule(): void {
    if (!frame && alive) frame = requestAnimationFrame(draw);
  }

  function moved(): void {
    clampView();
    schedule();
    opts.onMove?.();
  }

  function zoomAt(sx: number, sy: number, delta: number): void {
    const [wx, wy] = fromScreen(sx, sy);
    zoom = Math.min(MAX_ZOOM, Math.max(minZoom(), zoom + delta));
    cx = wx - (sx - width / 2) / scale();
    cy = wy - (sy - height / 2) / scale();
    moved();
  }

  function fitBox(south: number, west: number, north: number, east: number): void {
    const [x0, y1] = project(south, west);
    const [x1, y0] = project(north, east);
    const spanX = Math.max(1e-6, x1 - x0);
    const spanY = Math.max(1e-6, y1 - y0);
    cx = (x0 + x1) / 2;
    cy = (y0 + y1) / 2;
    zoom = Math.min(MAX_ZOOM - 3, Math.log2(Math.min((width * 0.75) / (spanX * TILE), (height * 0.75) / (spanY * TILE))));
    moved();
  }

  let drag: { x: number; y: number; cx: number; cy: number; moved: boolean } | null = null;
  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture(event.pointerId);
    drag = { x: event.clientX, y: event.clientY, cx, cy, moved: false };
  });
  canvas.addEventListener("pointermove", (event) => {
    const rect = canvas.getBoundingClientRect();
    const sx = event.clientX - rect.left;
    const sy = event.clientY - rect.top;
    if (drag) {
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      if (drag.moved) {
        cx = drag.cx - dx / scale();
        cy = drag.cy - dy / scale();
        moved();
      }
      return;
    }
    canvas.classList.toggle("over-marker", hitAt(sx, sy) !== null);
  });
  canvas.addEventListener("pointerup", (event) => {
    const wasDrag = drag?.moved;
    drag = null;
    if (wasDrag) return;
    const rect = canvas.getBoundingClientRect();
    const sx = event.clientX - rect.left;
    const sy = event.clientY - rect.top;
    const hit = hitAt(sx, sy);
    if (hit) {
      const [s, w, n, e] = hit.bx;
      if (hit.ids.length > 1 && zoom < MAX_ZOOM - 3 && (n - s > 1e-4 || e - w > 1e-4)) fitBox(s, w, n, e);
      else opts.onOpen?.(hit.ids);
      return;
    }
    if (opts.onPick) {
      const [x, y] = fromScreen(sx, sy);
      const [lat, lon] = unproject(((x % 1) + 1) % 1, y);
      opts.onPick(lat, lon);
    }
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    zoomAt(event.clientX - rect.left, event.clientY - rect.top, -event.deltaY * (event.ctrlKey ? 0.01 : 0.0025));
  }, { passive: false });
  canvas.addEventListener("dblclick", (event) => {
    const rect = canvas.getBoundingClientRect();
    zoomAt(event.clientX - rect.left, event.clientY - rect.top, event.shiftKey ? -1 : 1);
  });
  zoomIn.addEventListener("click", () => zoomAt(width / 2, height / 2, 1));
  zoomOut.addEventListener("click", () => zoomAt(width / 2, height / 2, -1));

  function hitAt(sx: number, sy: number): (typeof hits)[number] | null {
    for (let i = hits.length - 1; i >= 0; i--) {
      if (Math.abs(hits[i].x - sx) <= THUMB / 2 + 2 && Math.abs(hits[i].y - sy) <= THUMB / 2 + 2) return hits[i];
    }
    return null;
  }

  let pendingFit: MapPoint[] | null | undefined;
  const resize = new ResizeObserver(() => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    dpr = window.devicePixelRatio || 1;
    width = rect.width;
    height = rect.height;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    if (pendingFit !== undefined) {
      const target = pendingFit;
      pendingFit = undefined;
      view.fit(target ?? undefined);
    } else {
      clampView();
      draw();
    }
  });
  resize.observe(el);
  void world().then((data) => {
    land = data;
    schedule();
  });

  const view: MapView = {
    el,
    setPoints(next) {
      points = next;
      projected = new Float64Array(next.length * 2);
      next.forEach((p, i) => {
        const [x, y] = project(p[1], p[2]);
        projected[i * 2] = x;
        projected[i * 2 + 1] = y;
      });
      schedule();
    },
    fit(target) {
      if (width === 0) {
        pendingFit = target ?? null;
        return;
      }
      const list = target ?? points;
      if (!list.length) {
        zoom = minZoom();
        cx = 0.5;
        cy = 0.42;
        moved();
        return;
      }
      let s = 90;
      let w = 180;
      let n = -90;
      let e = -180;
      for (const p of list) {
        s = Math.min(s, p[1]);
        n = Math.max(n, p[1]);
        w = Math.min(w, p[2]);
        e = Math.max(e, p[2]);
      }
      const pad = 0.02;
      fitBox(s - pad, w - pad, n + pad, e + pad);
    },
    center(lat, lon, z) {
      [cx, cy] = project(lat, lon);
      if (z !== undefined) zoom = z;
      if (width === 0) pendingFit = undefined;
      moved();
    },
    setPin(lat, lon) {
      pin = lat === null || lon === null ? null : [lat, lon];
      schedule();
    },
    bounds() {
      const [x0, y0] = fromScreen(0, 0);
      const [x1, y1] = fromScreen(width, height);
      const [north, west] = unproject(((x0 % 1) + 1) % 1, Math.max(0, y0));
      const [south, east] = unproject(((x1 % 1) + 1) % 1, Math.min(1, y1));
      if (x1 - x0 >= 1) return [south, -180, north, 180];
      return [south, west, north, east];
    },
    destroy() {
      alive = false;
      resize.disconnect();
      if (frame) cancelAnimationFrame(frame);
    },
  };
  return view;
}
