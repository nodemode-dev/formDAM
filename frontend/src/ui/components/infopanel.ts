import { api } from "../../engine/api.js";
import { formatDuration, fullStamp, humanBytes } from "../../engine/format.js";
import { keywordState, loadKeywords, navigate, on, patched, saveMeta, state } from "../../engine/store.js";
import type { MediaDetails } from "../../engine/types.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { toast } from "../toast.js";

export const LABELS = ["red", "orange", "yellow", "green", "blue", "purple", "gray"] as const;

export interface InfoPanel {
  el: HTMLElement;
  show: (id: number) => void;
  refresh: () => void;
}

interface Row {
  wrap: HTMLElement;
  value: HTMLElement;
}

function row(label: string): Row {
  const value = h("span", { class: "info-v" }, "");
  const wrap = h("div", { class: "info-row" }, h("span", { class: "info-k" }, label), value);
  return { wrap, value };
}

function shutterText(s: number | null | undefined): string {
  if (!s) return "";
  return s >= 1 ? `${s.toFixed(1).replace(/\.0$/, "")} s` : `1/${Math.round(1 / s)} s`;
}

function exposureLine(d: MediaDetails): string {
  const parts: string[] = [];
  if (d.aperture) parts.push(`f/${d.aperture.toFixed(1).replace(/\.0$/, "")}`);
  if (d.shutter) parts.push(shutterText(d.shutter));
  if (d.iso) parts.push(`ISO ${d.iso}`);
  if (d.focal) parts.push(`${Math.round(d.focal)} mm${d.focal35 ? ` (${Math.round(d.focal35)} mm eq.)` : ""}`);
  if (d.flash) parts.push("Flash");
  return parts.join(" · ");
}

function typeLine(d: MediaDetails): string {
  const flags: string[] = [];
  if (d.kind === "video") flags.push("Video");
  else if (d.live_video_id) flags.push("Live Photo");
  else flags.push("Photo");
  if (d.is_raw) flags.push("RAW");
  if (d.is_panorama) flags.push("Panorama");
  if (d.is_selfie) flags.push("Selfie");
  if (d.is_portrait) flags.push("Portrait");
  if (d.is_slomo) flags.push("Slo-mo");
  if (d.burst_id) flags.push("Burst");
  if (d.is_screenshot) flags.push("Screenshot");
  if (d.is_screen_rec) flags.push("Screen Recording");
  return flags.join(" · ");
}

export function createInfoPanel(onLocationEdit?: (id: number) => void, onDateEdit?: (id: number) => void): InfoPanel {
  let currentId: number | null = null;
  let current: MediaDetails | null = null;
  let seq = 0;

  const stars = h("div", { class: "rate-row", role: "radiogroup", "aria-label": "Rating" });
  const starBtns: HTMLButtonElement[] = [];
  for (let n = 1; n <= 5; n++) {
    const btn = h("button", { class: "star-btn", type: "button", "aria-label": `${n} star${n > 1 ? "s" : ""}` }, iconEl("star")) as HTMLButtonElement;
    btn.addEventListener("click", () => {
      if (!current) return;
      const next = current.rating === n ? 0 : n;
      void commit({ rating: next });
    });
    starBtns.push(btn);
    stars.append(btn);
  }
  const rejectBtn = h("button", { class: "icon-btn reject-btn", type: "button", "aria-label": "Reject", title: "Reject (X)" }, iconEl("flag")) as HTMLButtonElement;
  rejectBtn.addEventListener("click", () => {
    if (current) void commit({ rejected: !current.rejected });
  });
  stars.append(h("span", { class: "head-spacer" }), rejectBtn);

  const labels = h("div", { class: "label-row", role: "radiogroup", "aria-label": "Colour label" });
  const labelBtns = new Map<string, HTMLButtonElement>();
  const noneBtn = h("button", { class: "label-dot none", type: "button", "aria-label": "No label" }) as HTMLButtonElement;
  noneBtn.addEventListener("click", () => current && void commit({ label: "" }));
  labelBtns.set("", noneBtn);
  labels.append(noneBtn);
  for (const name of LABELS) {
    const btn = h("button", { class: `label-dot l-${name}`, type: "button", "aria-label": `${name} label`, title: name }) as HTMLButtonElement;
    btn.addEventListener("click", () => current && void commit({ label: current.label === name ? "" : name }));
    labelBtns.set(name, btn);
    labels.append(btn);
  }

  function textArea(placeholder: string, field: "title" | "caption" | "alt_text", rows = 1): HTMLTextAreaElement {
    const area = h("textarea", { class: "info-input", rows: String(rows), placeholder, spellcheck: "true" }) as HTMLTextAreaElement;
    area.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" && !event.shiftKey && field === "title") || event.key === "Escape") {
        event.preventDefault();
        area.blur();
      }
      event.stopPropagation();
    });
    area.addEventListener("blur", () => {
      if (!current) return;
      const value = area.value.trim();
      if ((current[field] ?? "") === value) return;
      void commit({ [field]: value });
    });
    return area;
  }
  const titleIn = textArea("Add a title", "title");
  const captionIn = textArea("Add a caption", "caption", 2);
  const altIn = textArea("Describe this image for screen readers", "alt_text", 2);

  const kwList = h("div", { class: "chip-list" });
  const kwInput = h("input", { class: "info-input kw-input", placeholder: "Add keyword", list: "dam-kw-list", spellcheck: "false", autocomplete: "off" }) as HTMLInputElement;
  const kwData = h("datalist", { id: "dam-kw-list" });
  kwInput.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Escape") {
      kwInput.blur();
      return;
    }
    if (event.key !== "Enter" || !kwInput.value.trim() || currentId === null) return;
    const name = kwInput.value.trim();
    kwInput.value = "";
    void addKeyword(currentId, name);
  });
  function syncKwData(): void {
    patchList(kwData, keywordState.list, (k) => String(k.id), (k) => h("option", { value: k.name }));
  }

  const peopleList = h("div", { class: "chip-list" });
  const subjectList = h("div", { class: "chip-list" });
  const albumList = h("div", { class: "chip-list" });

  const rCaptured = row("Captured");
  const dateBtn = h("button", { class: "link-btn", type: "button" }, "Adjust") as HTMLButtonElement;
  dateBtn.addEventListener("click", () => currentId !== null && onDateEdit?.(currentId));
  rCaptured.wrap.firstElementChild!.append(dateBtn);
  const rPlace = row("Location");
  const placeBtn = h("button", { class: "link-btn", type: "button" }, "Edit") as HTMLButtonElement;
  placeBtn.addEventListener("click", () => currentId !== null && onLocationEdit?.(currentId));
  rPlace.wrap.firstElementChild!.append(placeBtn);
  const rCamera = row("Camera");
  const rLens = row("Lens");
  const rExposure = row("Exposure");
  const rType = row("Type");
  const rFile = row("File");
  const rDims = row("Dimensions");
  const rSize = row("Size");
  const rDuration = row("Duration");
  const rImported = row("Imported");
  const exifTable = h("div", { class: "exif-table" });
  const exifToggle = h("button", { class: "link-btn", type: "button" }, "Show all metadata") as HTMLButtonElement;
  let exifOpen = false;
  exifToggle.addEventListener("click", () => {
    exifOpen = !exifOpen;
    exifTable.classList.toggle("hidden", !exifOpen);
    setText(exifToggle, exifOpen ? "Hide all metadata" : "Show all metadata");
  });
  exifTable.classList.add("hidden");

  const section = (title: string, ...kids: HTMLElement[]) =>
    h("div", { class: "info-section" }, h("div", { class: "info-k" }, title), ...kids);

  const el = h("div", { class: "info-panel hidden" },
    stars, labels, titleIn, captionIn,
    section("Keywords", kwList, kwInput, kwData),
    section("People", peopleList),
    section("Subjects", subjectList),
    rCaptured.wrap, rPlace.wrap, rCamera.wrap, rLens.wrap, rExposure.wrap,
    rType.wrap, rFile.wrap, rDims.wrap, rSize.wrap, rDuration.wrap, rImported.wrap,
    section("Albums", albumList),
    section("Accessibility", altIn),
    exifToggle, exifTable,
  );

  function paint(): void {
    const d = current;
    if (!d) return;
    starBtns.forEach((btn, i) => btn.classList.toggle("on", (d.rating ?? 0) > i));
    rejectBtn.classList.toggle("active", Boolean(d.rejected));
    for (const [name, btn] of labelBtns) btn.classList.toggle("on", (d.label ?? "") === name);
    if (document.activeElement !== titleIn) titleIn.value = d.title ?? "";
    if (document.activeElement !== captionIn) captionIn.value = d.caption ?? "";
    if (document.activeElement !== altIn) altIn.value = d.alt_text ?? "";
    patchList(kwList, d.keywords, (k) => String(k.id), (k) => {
      const chip = h("span", { class: "chip" }, h("span", { class: "chip-text" }, k.name));
      const x = h("button", { class: "chip-x", type: "button", "aria-label": `Remove ${k.name}` }, iconEl("close"));
      x.addEventListener("click", () => currentId !== null && void removeKeyword(currentId, k.id));
      chip.append(x);
      return chip;
    });
    patchList(peopleList, d.people, (p) => String(p.id), (p) => {
      const chip = h("button", { class: "chip link", type: "button" }, p.name ?? "Unnamed");
      chip.addEventListener("click", () => navigate(`#/person/${p.id}`));
      return chip;
    });
    patchList(subjectList, d.subjects, (s) => s.label, (s) => {
      const chip = h("button", { class: "chip link", type: "button" }, s.label);
      chip.addEventListener("click", () => navigate(`#/search/${encodeURIComponent(s.label)}`));
      return chip;
    });
    patchList(albumList, d.albums ?? [], (a) => String(a.id), (a) => {
      const chip = h("button", { class: "chip link", type: "button" }, a.name);
      chip.addEventListener("click", () => navigate(`#/album/${a.id}`));
      return chip;
    });
    peopleList.parentElement!.classList.toggle("hidden", d.people.length === 0);
    subjectList.parentElement!.classList.toggle("hidden", d.subjects.length === 0);
    albumList.parentElement!.classList.toggle("hidden", (d.albums ?? []).length === 0);
    setText(rCaptured.value, `${fullStamp(d.created_ts)}${d.created_src === "exif" ? "" : d.created_src === "adjusted" ? " (adjusted)" : " (from file)"}`);
    const where = [d.place, d.admin, d.country].filter(Boolean).join(", ");
    const coords = d.lat !== null && d.lat !== undefined && d.lon !== null && d.lon !== undefined ? `${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}` : "";
    setText(rPlace.value, where ? `${where}${coords ? `\n${coords}` : ""}` : coords || "No location");
    const camera = [d.make, d.model].filter(Boolean).join(" ").trim();
    setText(rCamera.value, camera);
    rCamera.wrap.classList.toggle("hidden", !camera);
    setText(rLens.value, d.lens ?? "");
    rLens.wrap.classList.toggle("hidden", !d.lens);
    const exposure = exposureLine(d);
    setText(rExposure.value, exposure);
    rExposure.wrap.classList.toggle("hidden", !exposure);
    setText(rType.value, typeLine(d));
    setText(rFile.value, d.name);
    setText(rDims.value, d.width && d.height ? `${d.width} x ${d.height} (${((d.width * d.height) / 1e6).toFixed(1)} MP)` : "Unknown");
    setText(rSize.value, humanBytes(d.size));
    setText(rDuration.value, d.duration ? formatDuration(d.duration) : "");
    rDuration.wrap.classList.toggle("hidden", !d.duration);
    setText(rImported.value, `${fullStamp(d.imported_ts)}${d.batch ? ` · ${d.batch.label ?? d.batch.source}` : ""}`);
    const exifRows = Object.entries(d.exif ?? {}).sort(([a], [b]) => a.localeCompare(b));
    patchList(exifTable, exifRows, ([k]) => k, ([k, v]) =>
      h("div", { class: "exif-row" }, h("span", { class: "exif-k" }, k), h("span", { class: "exif-v" }, v)),
    (node, [, v]) => setText(node.lastElementChild as HTMLElement, v));
    exifToggle.classList.toggle("hidden", exifRows.length === 0);
  }

  async function load(id: number): Promise<void> {
    const mine = ++seq;
    const data = await api<MediaDetails>(`/media/${id}/details`);
    if (mine !== seq || currentId !== id) return;
    current = data;
    const cached = state.byId.get(id);
    if (cached) Object.assign(cached, { ...data, exif: undefined, iptc: undefined });
    paint();
  }

  async function commit(fields: Record<string, unknown>): Promise<void> {
    if (currentId === null) return;
    const id = currentId;
    try {
      await saveMeta([id], fields);
    } catch (err) {
      toast(String((err as Error).message), "error");
      return;
    }
    if (current && currentId === id) {
      Object.assign(current, fields, "rejected" in fields ? { rejected: fields.rejected ? 1 : 0 } : {});
      paint();
    }
  }

  async function addKeyword(id: number, name: string): Promise<void> {
    await api("/media/keywords", { method: "POST", body: JSON.stringify({ ids: [id], add: [name] }) });
    void loadKeywords();
    if (currentId === id) await load(id);
  }

  async function removeKeyword(id: number, keywordId: number): Promise<void> {
    await api("/media/keywords", { method: "POST", body: JSON.stringify({ ids: [id], remove: [keywordId] }) });
    void loadKeywords();
    if (currentId === id) await load(id);
  }

  on("keywords", syncKwData);
  on("meta", () => {
    if (currentId !== null && patched.ids.includes(currentId) && current) {
      const fresh = state.byId.get(currentId);
      if (fresh) {
        Object.assign(current, {
          rating: fresh.rating, label: fresh.label, rejected: fresh.rejected, title: fresh.title,
          caption: fresh.caption, alt_text: fresh.alt_text, favorite: fresh.favorite, created_ts: fresh.created_ts,
          created_src: fresh.created_src, lat: fresh.lat, lon: fresh.lon, place: fresh.place, admin: fresh.admin, country: fresh.country,
        });
        paint();
      }
    }
  });
  if (!keywordState.loaded) void loadKeywords();
  else syncKwData();

  return {
    el,
    show(id: number) {
      if (currentId !== id) {
        currentId = id;
        void load(id);
      }
    },
    refresh() {
      if (currentId !== null) void load(currentId);
    },
  };
}
