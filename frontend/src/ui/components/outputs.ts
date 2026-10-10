import { api } from "../../engine/api.js";
import { countFmt } from "../../engine/format.js";
import { patchMedia, pollJob, state } from "../../engine/store.js";
import type { Media } from "../../engine/types.js";
import { type CtxEntry, openContextMenu } from "../contextmenu.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { openModal } from "../modal.js";
import { promptText } from "../prompt.js";
import { toast } from "../toast.js";
import { tileHooks } from "./grid.js";
import { selectbarExtras } from "./selectbar.js";
import { viewerHooks } from "./viewer.js";

interface Template { id: number; name: string; fields: Record<string, string> }
interface Workflow { id: number; name: string; steps: Array<Record<string, unknown>> }

const SECTIONS: Array<{ title: string; fields: Array<[string, string, "line" | "area" | "status"]> }> = [
  { title: "Description", fields: [["title", "Title", "line"], ["headline", "Headline", "line"], ["caption", "Description", "area"], ["altText", "Alt Text (Accessibility)", "area"], ["extendedDescription", "Extended Description", "area"]] },
  { title: "Creator & Rights", fields: [["creator", "Creator", "line"], ["creatorJob", "Creator Job Title", "line"], ["copyright", "Copyright Notice", "line"], ["copyrightStatus", "Copyright Status", "status"], ["rightsUsage", "Rights Usage Terms", "area"], ["copyrightUrl", "Copyright Info URL", "line"], ["credit", "Credit Line", "line"], ["source", "Source", "line"]] },
  { title: "Contact", fields: [["creatorAddress", "Address", "line"], ["creatorCity", "City", "line"], ["creatorState", "State / Province", "line"], ["creatorCountry", "Country", "line"], ["creatorEmail", "Email", "line"], ["creatorPhone", "Phone", "line"], ["creatorUrl", "Website", "line"]] },
  { title: "Location & Status", fields: [["sublocation", "Sublocation", "line"], ["city", "City", "line"], ["state", "State / Province", "line"], ["country", "Country", "line"], ["isoCountryCode", "ISO Country Code", "line"], ["event", "Event", "line"], ["personShown", "People Shown", "line"], ["scene", "IPTC Scene Codes", "line"], ["subjectCode", "IPTC Subject Codes", "line"], ["intellectualGenre", "Genre", "line"], ["jobId", "Job Identifier", "line"], ["instructions", "Instructions", "area"]] },
];

function idsFor(item: Media): number[] {
  return state.selection.has(item.id) && state.selection.size > 1 ? [...state.selection] : [item.id];
}

function check(label: string, value: boolean): { wrap: HTMLElement; input: HTMLInputElement } {
  const input = h("input", { type: "checkbox" }) as HTMLInputElement;
  input.checked = value;
  return { wrap: h("label", { class: "field-check" }, input, label), input };
}

function select(options: Array<[string, string]>, value: string): HTMLSelectElement {
  const el = h("select", { class: "field-input" }) as HTMLSelectElement;
  for (const [v, label] of options) el.append(h("option", { value: v }, label));
  el.value = value;
  return el;
}

function field(label: string, control: HTMLElement): HTMLElement {
  return h("label", { class: "field" }, h("span", { class: "field-label" }, label), control);
}

function stop<T extends HTMLElement>(el: T): T {
  el.addEventListener("keydown", (event) => event.stopPropagation());
  return el;
}

export async function pickFolder(title: string): Promise<string> {
  try {
    return (await api<{ path: string | null }>("/fs/pick", { method: "POST" })).path ?? "";
  } catch {
    return (await promptText(title, "~/Pictures/DAM Export", "Full path of a folder on this computer")) ?? "";
  }
}

export async function fileInfoFlow(ids: number[]): Promise<void> {
  const modal = openModal(ids.length === 1 ? "File Info" : `File Info for ${countFmt(ids.length)} Items`, 720);
  const [common, tpls, xmp] = await Promise.all([
    api<{ fields: Record<string, string>; mixed: string[]; place: { place: string | null; admin: string | null; country: string | null } | null }>("/fileinfo/common", { method: "POST", body: JSON.stringify({ ids }) }),
    api<{ templates: Template[] }>("/metadata-templates"),
    api<{ auto: boolean; pending: number }>("/xmp/settings"),
  ]);
  const dirty = new Set<string>();
  const inputs = new Map<string, HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>();
  const body = h("div", { class: "fileinfo" });
  for (const sec of SECTIONS) {
    const grid = h("div", { class: "fileinfo-grid" });
    for (const [key, label, kind] of sec.fields) {
      let control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
      if (kind === "area") control = stop(h("textarea", { class: "field-input info-input", rows: "2" }) as HTMLTextAreaElement);
      else if (kind === "status") control = select([["", "Unknown"], ["Copyrighted", "Copyrighted"], ["Public Domain", "Public Domain"]], "");
      else control = stop(h("input", { class: "field-input", spellcheck: "false", autocomplete: "off" }) as HTMLInputElement);
      control.value = common.fields[key] ?? "";
      if (common.mixed.includes(key)) control.setAttribute("placeholder", "Multiple values");
      else if (common.place && !control.value) {
        const hint = key === "city" ? common.place.place : key === "state" ? common.place.admin : key === "country" ? common.place.country : null;
        if (hint) control.setAttribute("placeholder", hint);
      }
      const mark = () => dirty.add(key);
      control.addEventListener("input", mark);
      control.addEventListener("change", mark);
      inputs.set(key, control);
      grid.append(h("label", { class: `field${kind === "area" ? " wide" : ""}` }, h("span", { class: "field-label" }, label), control));
    }
    body.append(h("div", { class: "ed-sec-title" }, sec.title), grid);
  }
  const tplSel = select([["", "Apply Template..."], ...tpls.templates.map((t) => [String(t.id), t.name] as [string, string])], "");
  tplSel.addEventListener("change", () => {
    const tpl = tpls.templates.find((t) => String(t.id) === tplSel.value);
    if (!tpl) return;
    for (const [key, value] of Object.entries(tpl.fields)) {
      const control = inputs.get(key);
      if (control && value) {
        control.value = value;
        dirty.add(key);
      }
    }
    tplSel.value = "";
  });
  const saveTpl = h("button", { class: "btn", type: "button" }, "Save as Template");
  saveTpl.addEventListener("click", async () => {
    const name = await promptText("Save Metadata Template", "", "Saves every filled field except title, description and alt text", "Save");
    if (!name) return;
    const fields: Record<string, string> = {};
    for (const [key, control] of inputs) if (control.value && !["title", "caption", "altText"].includes(key)) fields[key] = control.value;
    await api("/metadata-templates", { method: "POST", body: JSON.stringify({ name, fields }) });
    toast(`Template "${name}" saved`);
  });
  const auto = check("Keep XMP sidecars beside the originals up to date", xmp.auto);
  auto.input.addEventListener("change", () => void api("/xmp/settings", { method: "PUT", body: JSON.stringify({ auto: auto.input.checked }) }));
  const cancel = h("button", { class: "btn", type: "button" }, "Cancel");
  cancel.addEventListener("click", modal.close);
  const save = h("button", { class: "btn primary", type: "button" }, "Save");
  save.addEventListener("click", async () => {
    if (dirty.size === 0) {
      modal.close();
      return;
    }
    const fields: Record<string, string> = {};
    for (const key of dirty) fields[key] = inputs.get(key)?.value ?? "";
    await api("/fileinfo", { method: "POST", body: JSON.stringify({ ids, fields }) });
    const local: Partial<Media> = {};
    if (dirty.has("title")) local.title = fields.title || null;
    if (dirty.has("caption")) local.caption = fields.caption || null;
    if (dirty.has("altText")) local.alt_text = fields.altText || null;
    patchMedia(ids, local);
    viewerHooks.refreshInfo?.();
    toast(`Saved ${dirty.size} field${dirty.size === 1 ? "" : "s"} to ${countFmt(ids.length)} item${ids.length === 1 ? "" : "s"}`);
    modal.close();
  });
  modal.body.append(body, h("div", { class: "modal-foot" }, tplSel, saveTpl, h("span", { class: "head-spacer" }), cancel, save), auto.wrap);
}

export function exportFlow(ids: number[]): void {
  const modal = openModal(`Export ${countFmt(ids.length)} Item${ids.length === 1 ? "" : "s"}`, 560);
  const original = check("Export unmodified originals (no edits, original format)", false);
  const format = select([["jpeg", "JPEG"], ["heic", "HEIC"], ["png", "PNG"], ["tiff", "TIFF"], ["webp", "WebP"]], "jpeg");
  const quality = h("input", { type: "range", min: "40", max: "100", value: "90", class: "ed-range moved" }) as HTMLInputElement;
  const qVal = h("span", { class: "ed-val" }, "90");
  quality.addEventListener("input", () => setText(qVal, quality.value));
  const size = select([["full", "Full Size"], ["long", "Long Edge"], ["short", "Short Edge"], ["width", "Width"], ["height", "Height"]], "full");
  const px = stop(h("input", { class: "field-input", type: "number", min: "64", max: "20000", value: "2048" }) as HTMLInputElement);
  const naming = stop(h("input", { class: "field-input", spellcheck: "false", value: "{name}" }) as HTMLInputElement);
  const sub = select([["none", "None"], ["date", "Year / Date"], ["month", "Year / Month"], ["place", "Place"], ["album", "Album"]], "none");
  const meta = select([["all", "All metadata"], ["copyright", "Copyright and contact only"], ["none", "None"]], "all");
  const location = check("Include location", true);
  const sidecar = check("Write an XMP sidecar beside each file", false);
  const lossy = h("div", { class: "row-gap" }, field("Format", format), h("label", { class: "field" }, h("span", { class: "field-label" }, "Quality ", qVal), quality));
  const sizeRow = h("div", { class: "row-gap" }, field("Size", size), field("Pixels", px));
  const sync = () => {
    lossy.classList.toggle("hidden", original.input.checked);
    sizeRow.classList.toggle("hidden", original.input.checked);
    px.disabled = size.value === "full";
    quality.disabled = format.value === "png" || format.value === "tiff";
  };
  [original.input, size, format].forEach((el) => el.addEventListener("change", sync));
  sync();
  const cancel = h("button", { class: "btn", type: "button" }, "Cancel");
  cancel.addEventListener("click", modal.close);
  const go = h("button", { class: "btn primary", type: "button" }, "Export...");
  go.addEventListener("click", async () => {
    const dest = await pickFolder("Export to");
    if (!dest) return;
    const options = {
      original: original.input.checked, format: format.value, quality: Number(quality.value), size: size.value, px: Number(px.value),
      naming: naming.value || "{name}", subfolder: sub.value, metadata: meta.value, location: location.input.checked, sidecar: sidecar.input.checked,
    };
    const res = await api<{ job_id: string; dest: string }>("/export", { method: "POST", body: JSON.stringify({ ids, dest, options }) });
    modal.close();
    toast(`Exporting ${countFmt(ids.length)} item${ids.length === 1 ? "" : "s"}...`);
    pollJob(res.job_id, (job) => toast(`Exported ${countFmt(job.counts.exported ?? 0)} to ${res.dest}${job.counts.skipped ? ` (${countFmt(job.counts.skipped)} skipped)` : ""}`));
  });
  modal.body.append(original.wrap, lossy, sizeRow,
    field("File Name", naming), h("div", { class: "field-hint" }, "Tokens: {name} {seq:3} {date:%Y-%m-%d} {camera} {place} {title} {rating} {custom}"),
    h("div", { class: "row-gap" }, field("Subfolders", sub), field("Metadata", meta)), location.wrap, sidecar.wrap,
    h("div", { class: "modal-foot" }, h("span", { class: "head-spacer" }), cancel, go));
}

function pdfModal(title: string, path: string, ids: number[], options: Record<string, unknown>, controls: HTMLElement[], read: () => Record<string, unknown>): void {
  const modal = openModal(title, 760);
  const frame = h("iframe", { class: "pdf-frame", title }) as HTMLIFrameElement;
  const save = h("a", { class: "btn", download: `${title.toLowerCase().replace(/\s+/g, "-")}.pdf` }, iconEl("download"), "Save PDF");
  const print = h("button", { class: "btn primary", type: "button" }, iconEl("printer"), "Print...");
  let url = "";
  let seq = 0;
  const load = async () => {
    const mine = ++seq;
    const res = await fetch(`/api${path}`, { method: "POST", headers: { "content-type": "application/json", "x-dam-local": "1" }, body: JSON.stringify({ ids, options: { ...options, ...read() } }) });
    if (!res.ok || mine !== seq) return;
    const next = URL.createObjectURL(await res.blob());
    frame.src = next;
    save.setAttribute("href", next);
    if (url) URL.revokeObjectURL(url);
    url = next;
  };
  controls.forEach((c) => c.querySelectorAll("select, input").forEach((el) => el.addEventListener("change", () => void load())));
  print.addEventListener("click", () => frame.contentWindow?.print());
  modal.body.append(h("div", { class: "row-gap" }, ...controls), frame, h("div", { class: "modal-foot" }, h("span", { class: "head-spacer" }), save, print));
  void load();
}

export function contactSheetFlow(ids: number[]): void {
  const page = select([["a4", "A4"], ["letter", "US Letter"], ["a3", "A3"], ["tabloid", "Tabloid"]], "a4");
  const cols = select(["2", "3", "4", "5", "6", "8"].map((n) => [n, `${n} columns`] as [string, string]), "4");
  const caps = select([["name", "File names"], ["title", "Titles"], ["date", "Dates"], ["none", "No captions"]], "name");
  const landscape = check("Landscape", false);
  const title = stop(h("input", { class: "field-input", placeholder: "Sheet title" }) as HTMLInputElement);
  pdfModal("Contact Sheet", "/contact-sheet", ids, {}, [field("Page", page), field("Layout", cols), field("Captions", caps), field("Title", title), landscape.wrap],
    () => ({ page: page.value, columns: Number(cols.value), captions: caps.value, title: title.value, landscape: landscape.input.checked }));
}

export function printFlow(ids: number[]): void {
  const page = select([["letter", "US Letter"], ["a4", "A4"], ["a3", "A3"], ["tabloid", "Tabloid"]], "letter");
  const margin = select([["0", "Borderless"], ["0.03", "Narrow"], ["0.05", "Normal"], ["0.1", "Wide"]], "0.05");
  pdfModal("Print", "/print-sheet", ids, {}, [field("Paper", page), field("Margins", margin)], () => ({ page: page.value, margin: Number(margin.value) }));
}

const STEP_LABEL: Record<string, string> = { template: "Apply metadata template", keywords: "Add keywords", rating: "Set rating", label: "Set label", rename: "Rename files", sidecar: "Write XMP sidecars", export: "Export" };

export async function workflowsFlow(ids: number[]): Promise<void> {
  const modal = openModal("Workflows", 560);
  const list = h("div", { class: "list-rows" });
  const empty = h("div", { class: "field-hint" }, "A workflow runs saved steps over the selection: a metadata template, keywords, rating, rename, sidecars and an export.");
  const load = async () => {
    const res = await api<{ workflows: Workflow[] }>("/workflows");
    empty.classList.toggle("hidden", res.workflows.length > 0);
    patchList(list, res.workflows, (w) => String(w.id), (w) => {
      const run = h("button", { class: "btn primary", type: "button" }, `Run on ${countFmt(ids.length)}`);
      run.addEventListener("click", async () => {
        const job = await api<{ job_id: string }>(`/workflows/${w.id}/run`, { method: "POST", body: JSON.stringify({ ids }) });
        modal.close();
        toast(`Running ${w.name}...`);
        pollJob(job.job_id, (s) => toast(`${w.name}: ${s.phase === "done" ? "finished" : s.phase}`));
      });
      const del = h("button", { class: "icon-btn", type: "button", "aria-label": "Delete workflow" }, iconEl("trash"));
      del.addEventListener("click", async () => { await api(`/workflows/${w.id}`, { method: "DELETE" }); void load(); });
      return h("div", { class: "list-row glass-panel" }, iconEl("workflow"),
        h("div", { class: "list-title" }, w.name, h("div", { class: "field-hint" }, w.steps.map((s) => STEP_LABEL[String(s.kind)] ?? s.kind).join(" · "))), run, del);
    });
  };
  const add = h("button", { class: "btn", type: "button" }, iconEl("plus"), "New Workflow");
  add.addEventListener("click", () => { modal.close(); void newWorkflowFlow(ids); });
  modal.body.append(empty, list, h("div", { class: "modal-foot" }, h("span", { class: "head-spacer" }), add));
  await load();
}

async function newWorkflowFlow(ids: number[]): Promise<void> {
  const tpls = (await api<{ templates: Template[] }>("/metadata-templates")).templates;
  const modal = openModal("New Workflow", 600);
  const name = stop(h("input", { class: "field-input", value: "Deliver" }) as HTMLInputElement);
  const steps: Array<{ kind: string; read: () => Record<string, unknown> }> = [];
  const stepList = h("div", { class: "rule-list" });
  const addStep = (kind: string) => {
    let body: HTMLElement;
    let read: () => Record<string, unknown>;
    if (kind === "template") {
      const sel = select(tpls.map((t) => [String(t.id), t.name] as [string, string]), String(tpls[0]?.id ?? ""));
      const mode = select([["fill", "Fill empty fields"], ["replace", "Replace"]], "fill");
      body = h("div", { class: "row-gap" }, sel, mode);
      read = () => ({ template_id: Number(sel.value), mode: mode.value });
    } else if (kind === "keywords") {
      const input = stop(h("input", { class: "field-input", placeholder: "Comma separated; use | for hierarchy" }) as HTMLInputElement);
      body = input;
      read = () => ({ add: input.value.split(",").map((s) => s.trim()).filter(Boolean) });
    } else if (kind === "rating") {
      const sel = select(["0", "1", "2", "3", "4", "5"].map((n) => [n, n === "0" ? "No rating" : "★".repeat(Number(n))] as [string, string]), "3");
      body = sel;
      read = () => ({ value: Number(sel.value) });
    } else if (kind === "label") {
      const sel = select(["", "red", "orange", "yellow", "green", "blue", "purple", "gray"].map((l) => [l, l || "None"] as [string, string]), "green");
      body = sel;
      read = () => ({ value: sel.value });
    } else if (kind === "rename") {
      const input = stop(h("input", { class: "field-input", value: "{date:%Y%m%d}_{seq:3}" }) as HTMLInputElement);
      body = input;
      read = () => ({ template: input.value });
    } else if (kind === "export") {
      const dest = stop(h("input", { class: "field-input", value: "~/Pictures/DAM Export" }) as HTMLInputElement);
      const size = select([["full", "Full size"], ["long", "Long edge 2048"], ["long1080", "Long edge 1080"]], "long");
      body = h("div", { class: "row-gap" }, dest, size);
      read = () => ({ dest: dest.value, options: size.value === "full" ? {} : { size: "long", px: size.value === "long1080" ? 1080 : 2048 } });
    } else {
      body = h("span", { class: "field-hint" }, "Writes a sidecar beside each original");
      read = () => ({});
    }
    const entry = { kind, read };
    steps.push(entry);
    const remove = h("button", { class: "icon-btn", type: "button", "aria-label": "Remove step" }, iconEl("minus"));
    const row = h("div", { class: "wf-step" }, h("span", { class: "wf-kind" }, STEP_LABEL[kind]), body, remove);
    remove.addEventListener("click", () => { steps.splice(steps.indexOf(entry), 1); row.remove(); });
    stepList.append(row);
  };
  const kinds = select(Object.entries(STEP_LABEL).filter(([k]) => k !== "template" || tpls.length) as Array<[string, string]>, "keywords");
  const addBtn = h("button", { class: "btn", type: "button" }, iconEl("plus"), "Add Step");
  addBtn.addEventListener("click", () => addStep(kinds.value));
  const save = h("button", { class: "btn primary", type: "button" }, "Save");
  save.addEventListener("click", async () => {
    if (!steps.length) { toast("Add a step first"); return; }
    await api("/workflows", { method: "POST", body: JSON.stringify({ name: name.value.trim() || "Workflow", steps: steps.map((s) => ({ kind: s.kind, ...s.read() })) }) });
    modal.close();
    void workflowsFlow(ids);
  });
  modal.body.append(field("Name", name), stepList, h("div", { class: "row-gap" }, kinds, addBtn), h("div", { class: "modal-foot" }, h("span", { class: "head-spacer" }), save));
  addStep("keywords");
}

function outputMenu(ids: number[], x: number, y: number): void {
  openContextMenu(x, y, outputEntries(ids));
}

function outputEntries(ids: number[]): CtxEntry[] {
  return [
    { label: "File Info...", icon: "doc", action: () => void fileInfoFlow(ids) },
    { label: "Export...", icon: "export", action: () => exportFlow(ids) },
    { label: "Contact Sheet...", icon: "grid", action: () => contactSheetFlow(ids) },
    { label: "Print...", icon: "printer", action: () => printFlow(ids) },
    { label: "Workflows...", icon: "workflow", action: () => void workflowsFlow(ids) },
    { label: "Write XMP Sidecars", icon: "save", action: async () => {
      const res = await api<{ job_id: string }>("/xmp/write", { method: "POST", body: JSON.stringify({ ids }) });
      pollJob(res.job_id, (job) => toast(`Wrote ${countFmt(job.counts.written ?? 0)} sidecar${(job.counts.written ?? 0) === 1 ? "" : "s"}`));
    } },
    { label: "Read Metadata from Files", icon: "refresh", action: async () => {
      const res = await api<{ read: number }>("/xmp/read", { method: "POST", body: JSON.stringify({ ids }) });
      toast(`Read metadata for ${countFmt(res.read)} item${res.read === 1 ? "" : "s"}`);
    } },
  ];
}

let registered = false;

export function registerOutputs(): void {
  if (registered) return;
  registered = true;
  tileHooks.ctx.push((item) => outputEntries(idsFor(item)).slice(0, 4));
  selectbarExtras.push({ label: "Output", icon: "export", handler: (ids) => {
    const bar = document.querySelector<HTMLElement>(".sel-bar");
    const rect = bar?.getBoundingClientRect();
    outputMenu(ids, rect ? rect.left + 120 : 200, rect ? rect.top - 260 : 200);
  } });
  viewerHooks.toolbar.push((current) => {
    const btn = h("button", { class: "icon-btn", type: "button", "aria-label": "Output" }, iconEl("export"));
    btn.addEventListener("click", () => {
      const id = current();
      if (id === null) return;
      const rect = btn.getBoundingClientRect();
      outputMenu([id], rect.left - 160, rect.bottom + 6);
    });
    return btn;
  });
  window.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey) || document.querySelector(".modal-backdrop, .editor")) return;
    const viewerId = state.viewer ? state.viewer.ids[state.viewer.index] : undefined;
    const ids = viewerId !== undefined ? [viewerId] : [...state.selection];
    if (!ids.length) return;
    const key = event.key.toLowerCase();
    if (event.shiftKey && key === "e") { event.preventDefault(); exportFlow(ids); }
    else if (event.altKey && (key === "i" || event.code === "KeyI")) { event.preventDefault(); void fileInfoFlow(ids); }
    else if (!event.shiftKey && key === "p") { event.preventDefault(); printFlow(ids); }
  });
}
