import { api, thumbVersions } from "../../engine/api.js";
import { countFmt } from "../../engine/format.js";
import {
  clearSelection, invalidateMedia, keywordState, loadAlbums, loadKeywords, navigate, on, patchMedia, pollJob, quickRules,
  saveMeta, setQuickFilter, specKey, state, type QueryRule, type QuerySpec,
} from "../../engine/store.js";
import type { AlbumFolder, Media } from "../../engine/types.js";
import { type CtxEntry, openContextMenu } from "../contextmenu.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { openModal } from "../modal.js";
import { promptText } from "../prompt.js";
import { toast } from "../toast.js";
import { tileHooks } from "./grid.js";
import { LABELS } from "./infopanel.js";
import { selectbarExtras } from "./selectbar.js";
import { ratingKey, viewerHooks } from "./viewer.js";

export function specHash(spec: QuerySpec & { title?: string }): string {
  return `#/q/${encodeURIComponent(JSON.stringify(spec))}`;
}

function field(label: string, control: HTMLElement): HTMLElement {
  return h("label", { class: "field" }, h("span", { class: "field-label" }, label), control);
}

function input(value = "", placeholder = ""): HTMLInputElement {
  const el = h("input", { class: "field-input", spellcheck: "false", autocomplete: "off", placeholder }) as HTMLInputElement;
  el.value = value;
  el.addEventListener("keydown", (event) => event.stopPropagation());
  return el;
}

function select(options: Array<[string, string]>, value: string): HTMLSelectElement {
  const el = h("select", { class: "field-input" }) as HTMLSelectElement;
  for (const [v, label] of options) el.append(h("option", { value: v }, label));
  el.value = value;
  return el;
}

function footer(...buttons: HTMLElement[]): HTMLElement {
  return h("div", { class: "modal-foot" }, h("span", { class: "head-spacer" }), ...buttons);
}

export function assignKeywordsFlow(ids: number[]): void {
  const modal = openModal(`Keywords for ${countFmt(ids.length)} item${ids.length === 1 ? "" : "s"}`, 440);
  const add = input("", "Add keywords, comma separated; use | for hierarchy");
  const list = h("div", { class: "chip-list wrap" });
  const removeIds = new Set<number>();
  const sync = () => patchList(list, keywordState.list.filter((k) => k.count > 0), (k) => String(k.id), (k) => {
    const chip = h("button", { class: "chip", type: "button" }, k.name);
    chip.addEventListener("click", () => {
      if (removeIds.has(k.id)) removeIds.delete(k.id);
      else removeIds.add(k.id);
      chip.classList.toggle("strike", removeIds.has(k.id));
    });
    return chip;
  });
  void loadKeywords().then(sync);
  const save = h("button", { class: "btn primary", type: "button" }, "Apply") as HTMLButtonElement;
  save.addEventListener("click", async () => {
    const names = add.value.split(",").map((s) => s.trim()).filter(Boolean);
    await api("/media/keywords", { method: "POST", body: JSON.stringify({ ids, add: names, remove: [...removeIds] }) });
    await loadKeywords();
    modal.close();
    toast(`Keywords updated on ${countFmt(ids.length)} item${ids.length === 1 ? "" : "s"}`);
  });
  modal.body.append(field("Add", add), h("div", { class: "field-label" }, "Tap a keyword to remove it from the selection"), list, footer(save));
  add.focus();
}

export function openKeywordManager(): void {
  const modal = openModal("Keyword Manager", 560);
  const tree = h("div", { class: "kw-tree" });
  const newIn = input("", "New keyword (Parent|Child makes a hierarchy)");
  const addBtn = h("button", { class: "btn", type: "button" }, iconEl("plus"), "Add") as HTMLButtonElement;
  const exportBtn = h("button", { class: "btn", type: "button" }, iconEl("download"), "Export") as HTMLButtonElement;
  const importBtn = h("button", { class: "btn", type: "button" }, iconEl("upload"), "Import") as HTMLButtonElement;
  addBtn.addEventListener("click", async () => {
    if (!newIn.value.trim()) return;
    await api("/keywords", { method: "POST", body: JSON.stringify({ name: newIn.value.trim() }) });
    newIn.value = "";
    void loadKeywords();
  });
  exportBtn.addEventListener("click", async () => {
    const res = await fetch("/api/keywords/export", { headers: { "x-dam-local": "1" } });
    const blob = new Blob([await res.text()], { type: "text/plain" });
    const a = h("a", { href: URL.createObjectURL(blob), download: "keywords.txt" }) as HTMLAnchorElement;
    a.click();
  });
  importBtn.addEventListener("click", () => {
    const file = h("input", { type: "file", accept: ".txt,text/plain" }) as HTMLInputElement;
    file.addEventListener("change", async () => {
      const text = await file.files?.[0]?.text();
      if (!text) return;
      const res = await api<{ created: number }>("/keywords/import", { method: "POST", body: JSON.stringify({ text }) });
      toast(`Imported ${countFmt(res.created)} keywords`);
      void loadKeywords();
    });
    file.click();
  });

  function depthOf(id: number): number {
    let depth = 0;
    let cur = keywordState.list.find((k) => k.id === id);
    const seen = new Set<number>();
    while (cur && cur.parent_id !== null && !seen.has(cur.id)) {
      seen.add(cur.id);
      depth += 1;
      cur = keywordState.list.find((k) => k.id === cur!.parent_id);
    }
    return depth;
  }

  function ordered(): typeof keywordState.list {
    const byParent = new Map<number | null, typeof keywordState.list>();
    for (const k of keywordState.list) {
      const list = byParent.get(k.parent_id) ?? [];
      list.push(k);
      byParent.set(k.parent_id, list);
    }
    const out: typeof keywordState.list = [];
    const seen = new Set<number>();
    const walk = (parent: number | null) => {
      for (const k of byParent.get(parent) ?? []) {
        if (seen.has(k.id)) continue;
        seen.add(k.id);
        out.push(k);
        walk(k.id);
      }
    };
    walk(null);
    for (const k of keywordState.list) if (!seen.has(k.id)) out.push(k);
    return out;
  }

  function rowFor(k: (typeof keywordState.list)[number]): HTMLElement {
    const name = h("span", { class: "kw-name" }, k.name);
    const count = h("span", { class: "kw-count" }, countFmt(k.count));
    const shortcut = h("span", { class: "kw-key" }, k.shortcut ? k.shortcut.toUpperCase() : "");
    const node = h("div", { class: "kw-row", tabindex: "0" }, name, shortcut, count);
    node.style.paddingLeft = `${8 + depthOf(k.id) * 16}px`;
    node.addEventListener("dblclick", () => navigate(specHash({ rules: [{ field: "keyword", value: k.id }], title: k.name } as QuerySpec)));
    node.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const others = keywordState.list.filter((o) => o.id !== k.id);
      openContextMenu(event.clientX, event.clientY, [
        { label: "Show Photos", icon: "image", action: () => { modal.close(); navigate(specHash({ rules: [{ field: "keyword", value: k.id }], title: k.name } as QuerySpec)); } },
        { label: "Rename...", icon: "rename", action: () => renameKeyword(k.id, k.name) },
        { label: "Move Into...", icon: "move", action: () => pickKeyword(others, "Move Into", async (target) => {
          await patch(k.id, { parent_id: target });
        }) },
        { label: "Move to Top Level", icon: "layers", action: () => void patch(k.id, { detach: true }) },
        { label: "Merge Into...", icon: "mergePeople", action: () => pickKeyword(others, "Merge Into", async (target) => {
          await api("/keywords/merge", { method: "POST", body: JSON.stringify({ into_id: target, from_ids: [k.id] }) });
          void loadKeywords();
        }) },
        { label: "Set Shortcut...", icon: "type", action: async () => {
          const key = await promptText("Keyboard shortcut", k.shortcut ?? "", "One letter or digit; with photos selected, press it to toggle this keyword. Empty clears it.");
          if (key !== null) void patch(k.id, { shortcut: key.slice(0, 1) });
        } },
        "sep",
        { label: "Delete Keyword", icon: "trash", danger: true, action: async () => {
          await api(`/keywords/${k.id}`, { method: "DELETE" });
          void loadKeywords();
        } },
      ]);
    });
    return node;
  }

  async function patch(id: number, body: Record<string, unknown>): Promise<void> {
    try {
      await api(`/keywords/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    } catch (err) {
      toast(String((err as Error).message), "error");
    }
    void loadKeywords();
  }

  async function renameKeyword(id: number, current: string): Promise<void> {
    const next = await promptText("Rename keyword", current);
    if (next && next.trim() && next.trim() !== current) void patch(id, { name: next.trim() });
  }

  const sync = () => patchList(tree, ordered(), (k) => String(k.id), rowFor, (node, k) => {
    setText(node.querySelector(".kw-name") as HTMLElement, k.name);
    setText(node.querySelector(".kw-count") as HTMLElement, countFmt(k.count));
    setText(node.querySelector(".kw-key") as HTMLElement, k.shortcut ? k.shortcut.toUpperCase() : "");
    node.style.paddingLeft = `${8 + depthOf(k.id) * 16}px`;
  });
  const off = on("keywords", sync);
  const closeOrig = modal.close;
  modal.close = () => {
    off();
    closeOrig();
  };
  modal.body.append(
    h("div", { class: "row-gap" }, newIn, addBtn),
    h("div", { class: "field-label" }, "Right-click a keyword to rename, nest, merge, set a shortcut or delete it. Double-click shows its photos."),
    tree,
    footer(importBtn, exportBtn),
  );
  void loadKeywords().then(sync);
}

function pickKeyword(options: typeof keywordState.list, title: string, done: (id: number) => Promise<void>): void {
  const modal = openModal(title, 360);
  const list = h("div", { class: "list-rows", style: "max-height:360px;overflow-y:auto" });
  for (const k of options) {
    const btn = h("button", { class: "list-row glass-panel", type: "button" }, iconEl("tag"), h("div", { class: "list-title" }, k.name));
    btn.addEventListener("click", async () => {
      modal.close();
      await done(k.id);
    });
    list.append(btn);
  }
  modal.body.append(list);
}

export function renameFlow(ids: number[]): void {
  const modal = openModal(`Rename ${countFmt(ids.length)} file${ids.length === 1 ? "" : "s"}`, 520);
  const template = input("{date:%Y-%m-%d}_{name}", "Template");
  const start = input("1");
  const custom = input("", "Text for {custom}");
  const preview = h("div", { class: "rename-preview" });
  let timer: number | undefined;
  const refresh = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const res = await api<{ plan: Array<{ id: number; old: string; new: string; ok: boolean; reason: string }> }>(
        "/media/rename/preview", { method: "POST", body: JSON.stringify({ ids: ids.slice(0, 8), template: template.value, start: Number(start.value) || 1, custom: custom.value }) });
      patchList(preview, res.plan, (p) => String(p.id), (p) => h("div", { class: "rename-row" }, h("span", { class: "r-old" }, p.old), h("span", { class: "r-new" }, p.new)),
        (node, p) => {
          setText(node.lastElementChild as HTMLElement, p.ok ? p.new : `${p.new} (${p.reason})`);
          node.classList.toggle("muted", !p.ok);
        });
    }, 180);
  };
  [template, start, custom].forEach((el) => el.addEventListener("input", refresh));
  const tokens = h("div", { class: "field-label" }, "Tokens: {name} {seq:3} {num} {date:%Y%m%d} {year} {month} {day} {camera} {lens} {iso} {title} {place} {country} {rating} {label} {custom}");
  const go = h("button", { class: "btn primary", type: "button" }, "Rename") as HTMLButtonElement;
  go.addEventListener("click", async () => {
    const res = await api<{ plan: Array<{ id: number; new: string; ok: boolean }> }>("/media/rename", {
      method: "POST", body: JSON.stringify({ ids, template: template.value, start: Number(start.value) || 1, custom: custom.value }) });
    const done = res.plan.filter((p) => p.ok);
    for (const p of done) {
      const item = state.byId.get(p.id);
      if (item) item.name = p.new;
    }
    modal.close();
    invalidateMedia();
    toast(`Renamed ${countFmt(done.length)} file${done.length === 1 ? "" : "s"}`);
  });
  modal.body.append(field("Template", template), tokens, h("div", { class: "row-gap" }, field("Start at", start), field("Custom text", custom)), preview, footer(go));
  refresh();
}

export async function copyToFlow(ids: number[]): Promise<void> {
  let dest = "";
  try {
    dest = (await api<{ path: string | null }>("/fs/pick", { method: "POST" })).path ?? "";
  } catch {
    dest = (await promptText("Copy originals to", "", "Full path of a folder on this computer")) ?? "";
  }
  if (!dest) return;
  const res = await api<{ job_id: string }>("/media/copy-to", { method: "POST", body: JSON.stringify({ ids, dest }) });
  pollJob(res.job_id, (job) => toast(`Copied ${countFmt(job.counts.copied ?? 0)} original${(job.counts.copied ?? 0) === 1 ? "" : "s"} to ${dest}`));
}

interface EditWithStatus { active: boolean; adopted: number; app?: string; edit_json?: string | null; edited_ts?: number | null }

const roundTrips = new Map<number, number>();

async function startEditWith(id: number, app?: string): Promise<void> {
  let res: EditWithStatus;
  try {
    res = await api<EditWithStatus>(`/media/${id}/edit-with`, { method: "POST", body: JSON.stringify(app ? { app } : {}) });
  } catch (err) {
    toast((err as Error).message || "Could not open the application");
    return;
  }
  const label = app ?? "the default app";
  toast(`Opened a copy in ${label}. Save it there and the change appears here.`);
  window.clearInterval(roundTrips.get(id));
  let seen = res.adopted;
  const started = Date.now();
  const timer = window.setInterval(() => {
    void api<EditWithStatus>(`/media/${id}/edit-with`).then((s) => {
      if (!s.active || Date.now() - started > 6 * 3600 * 1000) {
        window.clearInterval(timer);
        roundTrips.delete(id);
      }
      if (s.adopted > seen) {
        seen = s.adopted;
        thumbVersions.set(id, s.edited_ts ?? Date.now() / 1000);
        patchMedia([id], { edit_json: s.edit_json, edited_ts: s.edited_ts } as Partial<Media>);
        viewerHooks.reloadStill?.();
        toast(`Applied the edit from ${label}. Revert to Original undoes it.`);
      }
    }).catch(() => undefined);
  }, 2000);
  roundTrips.set(id, timer);
}

export async function openWithFlow(id: number): Promise<void> {
  const apps = (await api<{ apps: string[] }>("/system/editors")).apps;
  if (apps.length === 0) {
    await startEditWith(id);
    return;
  }
  const modal = openModal("Edit With", 380);
  const filter = input("", "Filter applications");
  const list = h("div", { class: "list-rows", style: "max-height:360px;overflow-y:auto" });
  const preferred = ["Preview", "Pixelmator Pro", "Affinity Photo 2", "Adobe Photoshop 2026", "FormVis", "FormLit"];
  const sorted = [...apps].sort((a, b) => (preferred.indexOf(b) - preferred.indexOf(a)) || a.localeCompare(b));
  const sync = () => patchList(list, sorted.filter((a) => a.toLowerCase().includes(filter.value.toLowerCase())), (a) => a, (app) => {
    const btn = h("button", { class: "list-row glass-panel", type: "button" }, iconEl("external"), h("div", { class: "list-title" }, app));
    btn.addEventListener("click", async () => {
      modal.close();
      await startEditWith(id, app);
    });
    return btn;
  });
  filter.addEventListener("input", sync);
  modal.body.append(filter, list);
  sync();
}

export async function stackFlow(ids: number[]): Promise<void> {
  await api("/stacks", { method: "POST", body: JSON.stringify({ ids }) });
  clearSelection();
  invalidateMedia();
  toast(`Stacked ${countFmt(ids.length)} items`);
}

const RULE_FIELDS: Array<[string, string]> = [
  ["flag", "Is"], ["rating", "Rating"], ["label", "Label"], ["keyword", "Keyword"], ["person", "Person"],
  ["album", "Album"], ["date", "Date"], ["recent_days", "In the last (days)"], ["filename", "Filename"],
  ["title", "Title"], ["caption", "Caption"], ["camera", "Camera"], ["lens", "Lens"], ["place", "Place"],
  ["text", "Text in photo"], ["subject", "Subject"], ["visual", "Looks like"], ["iso", "ISO"], ["aperture", "Aperture"], ["focal", "Focal length"],
];
const FLAG_VALUES: Array<[string, string]> = [
  ["favorite", "Favorite"], ["photo", "Photo"], ["video", "Video"], ["raw", "RAW"], ["live", "Live Photo"],
  ["panorama", "Panorama"], ["selfie", "Selfie"], ["portrait", "Portrait"], ["slomo", "Slo-mo"], ["burst", "Burst"],
  ["screenshot", "Screenshot"], ["screen_recording", "Screen Recording"], ["edited", "Edited"], ["rejected", "Rejected"],
  ["located", "Has location"], ["not_located", "No location"], ["not_in_album", "Not in an album"],
  ["has_keywords", "Has keywords"], ["no_keywords", "No keywords"], ["has_people", "Has people"], ["titled", "Has title"],
  ["captioned", "Has caption"], ["has_text", "Has text"], ["timelapse", "Time-lapse"], ["cinematic", "Cinematic"],
  ["spatial", "Spatial"], ["long_exposure", "Long Exposure"], ["animated", "Animated"],
];
const NUM_OPS: Array<[string, string]> = [[">=", "at least"], ["<=", "at most"], ["=", "is"], [">", "above"], ["<", "below"]];
const TEXT_OPS: Array<[string, string]> = [["contains", "contains"], ["is", "is"], ["starts", "starts with"], ["excludes", "does not contain"]];
const IS_OPS: Array<[string, string]> = [["=", "is"], ["not", "is not"]];

export function ruleEditor(rules: QueryRule[], onChange: () => void): HTMLElement {
  const list = h("div", { class: "rule-list" });
  let seq = 0;
  interface Live { key: string; rule: QueryRule }
  const live: Live[] = rules.map((rule) => ({ key: String(seq++), rule }));

  function valueControl(rule: QueryRule): HTMLElement {
    const f = rule.field;
    if (f === "flag") {
      const sel = select(FLAG_VALUES, String(rule.value ?? "favorite"));
      rule.value = sel.value;
      sel.addEventListener("change", () => { rule.value = sel.value; onChange(); });
      return sel;
    }
    if (f === "label") {
      const sel = select(LABELS.map((l) => [l, l[0].toUpperCase() + l.slice(1)] as [string, string]), String(rule.value ?? "red"));
      rule.value = sel.value;
      sel.addEventListener("change", () => { rule.value = sel.value; onChange(); });
      return sel;
    }
    if (f === "keyword") {
      const sel = select(keywordState.list.map((k) => [String(k.id), k.name] as [string, string]), String(rule.value ?? keywordState.list[0]?.id ?? ""));
      rule.value = Number(sel.value);
      sel.addEventListener("change", () => { rule.value = Number(sel.value); onChange(); });
      return sel;
    }
    if (f === "person") {
      const sel = select(state.people.map((p) => [String(p.id), p.name ?? `Person ${p.id}`] as [string, string]), String(rule.value ?? state.people[0]?.id ?? ""));
      rule.value = Number(sel.value);
      sel.addEventListener("change", () => { rule.value = Number(sel.value); onChange(); });
      return sel;
    }
    if (f === "album") {
      const sel = select(state.albums.filter((a) => !a.is_smart && !a.is_private).map((a) => [String(a.id), a.name] as [string, string]), String(rule.value ?? ""));
      rule.value = Number(sel.value);
      sel.addEventListener("change", () => { rule.value = Number(sel.value); onChange(); });
      return sel;
    }
    const text = input(rule.value === undefined ? "" : String(rule.value), f === "date" ? "2025, May 2025, 2025-05-04, last month" : "");
    text.addEventListener("input", () => {
      const numeric = ["rating", "iso", "aperture", "focal", "recent_days"].includes(f);
      rule.value = numeric ? Number(text.value) : text.value;
      onChange();
    });
    return text;
  }

  function opControl(rule: QueryRule): HTMLElement {
    const f = rule.field;
    const opts = ["rating", "iso", "aperture", "focal"].includes(f) ? NUM_OPS
      : ["filename", "title", "caption", "camera", "lens", "place", "text"].includes(f) ? TEXT_OPS
      : ["date", "recent_days"].includes(f) ? [["=", "is"] as [string, string]] : IS_OPS;
    const sel = select(opts, rule.op ?? opts[0][0]);
    rule.op = sel.value;
    sel.addEventListener("change", () => { rule.op = sel.value; onChange(); });
    return sel;
  }

  function create(entry: Live): HTMLElement {
    const node = h("div", { class: "rule-row" });
    const fieldSel = select(RULE_FIELDS, entry.rule.field);
    const opSlot = h("span", { class: "rule-slot" }, opControl(entry.rule));
    const valueSlot = h("span", { class: "rule-slot grow" }, valueControl(entry.rule));
    fieldSel.addEventListener("change", () => {
      entry.rule.field = fieldSel.value;
      entry.rule.value = undefined;
      entry.rule.op = undefined;
      opSlot.replaceChildren(opControl(entry.rule));
      valueSlot.replaceChildren(valueControl(entry.rule));
      onChange();
    });
    const remove = h("button", { class: "icon-btn", type: "button", "aria-label": "Remove rule" }, iconEl("minus"));
    remove.addEventListener("click", () => {
      const at = live.indexOf(entry);
      if (at >= 0) live.splice(at, 1);
      rules.splice(rules.indexOf(entry.rule), 1);
      sync();
      onChange();
    });
    node.append(fieldSel, opSlot, valueSlot, remove);
    return node;
  }

  const addBtn = h("button", { class: "btn", type: "button" }, iconEl("plus"), "Add Rule");
  addBtn.addEventListener("click", () => {
    const rule: QueryRule = { field: "flag", value: "favorite" };
    rules.push(rule);
    live.push({ key: String(seq++), rule });
    sync();
    onChange();
  });
  const sync = () => patchList(list, live, (e) => e.key, create);
  sync();
  return h("div", { class: "rule-editor" }, list, addBtn);
}

export function smartAlbumFlow(existing?: { id: number; name: string; rules?: { rules: Array<Record<string, unknown>>; match?: string } }): void {
  const modal = openModal(existing ? "Edit Smart Album" : "New Smart Album", 640);
  const name = input(existing?.name ?? "Smart Album");
  const rules: QueryRule[] = (existing?.rules?.rules as QueryRule[] | undefined)?.map((r) => ({ ...r })) ?? [{ field: "flag", value: "favorite" }];
  const match = select([["all", "all"], ["any", "any"]], existing?.rules?.match ?? "all");
  const count = h("span", { class: "rule-count" }, "");
  let timer: number | undefined;
  const recount = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const spec = { rules, match: match.value };
      const res = await api<{ count: number }>(`/browse/count?spec=${encodeURIComponent(JSON.stringify(spec))}`);
      setText(count, `${countFmt(res.count)} matching item${res.count === 1 ? "" : "s"}`);
    }, 200);
  };
  match.addEventListener("change", recount);
  const save = h("button", { class: "btn primary", type: "button" }, existing ? "Save" : "Create") as HTMLButtonElement;
  save.addEventListener("click", async () => {
    const body = JSON.stringify({ name: name.value.trim() || "Smart Album", rules, match: match.value });
    const res = existing
      ? await api<{ id: number }>(`/smart-albums/${existing.id}`, { method: "PUT", body })
      : await api<{ id: number }>("/smart-albums", { method: "POST", body });
    await loadAlbums();
    modal.close();
    navigate(`#/album/${res.id}`);
  });
  const ready = Promise.all([keywordState.loaded ? Promise.resolve() : loadKeywords()]);
  void ready.then(() => {
    modal.body.append(
      field("Name", name),
      h("div", { class: "row-gap" }, h("span", {}, "Match"), match, h("span", {}, "of the following rules")),
      ruleEditor(rules, recount),
      footer(count, save),
    );
    recount();
  });
}

export async function smartFromSpec(name: string, spec: QuerySpec & { text?: string; fields?: string[]; match?: string }): Promise<void> {
  const title = await promptText("Save as Smart Album", name, "The album updates itself as matching items arrive.", "Save");
  if (!title || !title.trim()) return;
  const rules: QueryRule[] = [...(spec.rules ?? [])];
  if (spec.text) rules.push({ field: "search", value: spec.text, fields: spec.fields } as QueryRule);
  const res = await api<{ id: number }>("/smart-albums", { method: "POST", body: JSON.stringify({ name: title.trim(), rules, match: spec.match ?? "all" }) });
  await loadAlbums();
  navigate(`#/album/${res.id}`);
}

export async function loadFolders(): Promise<AlbumFolder[]> {
  return (await api<{ folders: AlbumFolder[] }>("/album-folders")).folders;
}

export async function newFolderFlow(parentId: number | null = null): Promise<void> {
  const name = await promptText("New Folder", "New Folder", "", "Create");
  if (!name || !name.trim()) return;
  await api("/album-folders", { method: "POST", body: JSON.stringify({ name: name.trim(), parent_id: parentId }) });
  void loadAlbums();
}

export async function moveAlbumFlow(albumId: number): Promise<void> {
  const folders = await loadFolders();
  const modal = openModal("Move to Folder", 360);
  const list = h("div", { class: "list-rows" });
  const top = h("button", { class: "list-row glass-panel", type: "button" }, iconEl("albums"), h("div", { class: "list-title" }, "Top level"));
  top.addEventListener("click", async () => {
    await api(`/albums/${albumId}/folder`, { method: "POST", body: JSON.stringify({ folder_id: null }) });
    modal.close();
    void loadAlbums();
  });
  list.append(top);
  for (const folder of folders) {
    const row = h("button", { class: "list-row glass-panel", type: "button" }, iconEl("folder"), h("div", { class: "list-title" }, folder.name));
    row.addEventListener("click", async () => {
      await api(`/albums/${albumId}/folder`, { method: "POST", body: JSON.stringify({ folder_id: folder.id }) });
      modal.close();
      void loadAlbums();
    });
    list.append(row);
  }
  modal.body.append(list);
}

export function openQuickFilters(anchor: HTMLElement): void {
  const rect = anchor.getBoundingClientRect();
  const flags: Array<[string, string]> = [
    ["favorite", "Favorites"], ["photo", "Photos"], ["video", "Videos"], ["edited", "Edited"], ["raw", "RAW"],
    ["not_rejected", "Hide rejected"], ["located", "With location"], ["has_keywords", "With keywords"], ["not_in_album", "Not in an album"],
  ];
  const entries: CtxEntry[] = flags.map(([flag, label]) => ({
    label, icon: "check" as const, selected: state.quick.flags.includes(flag),
    action: () => {
      const has = state.quick.flags.includes(flag);
      setQuickFilter({ flags: has ? state.quick.flags.filter((f) => f !== flag) : [...state.quick.flags, flag] });
    },
  }));
  entries.push("sep");
  for (let n = 1; n <= 5; n++) {
    entries.push({
      label: `${"★".repeat(n)} or more`, selected: state.quick.minRating === n,
      action: () => setQuickFilter({ minRating: state.quick.minRating === n ? 0 : n }),
    });
  }
  entries.push("sep");
  for (const l of LABELS) {
    entries.push({ label: `${l[0].toUpperCase()}${l.slice(1)} label`, selected: state.quick.label === l, action: () => setQuickFilter({ label: state.quick.label === l ? "" : l }) });
  }
  if (quickRules().length) {
    entries.push("sep", { label: "Clear Filters", icon: "close", action: () => setQuickFilter({ flags: [], minRating: 0, label: "", keyword: "" }) });
  }
  openContextMenu(rect.left, rect.bottom + 6, entries);
}

function selectionIds(): number[] {
  return [...state.selection];
}

function tileEntries(item: Media): CtxEntry[] {
  const ids = state.selection.has(item.id) && state.selection.size > 1 ? selectionIds() : [item.id];
  const entries: CtxEntry[] = [
    { label: "Keywords...", icon: "tag", action: () => assignKeywordsFlow(ids) },
    { label: "Rename...", icon: "rename", action: () => renameFlow(ids) },
    { label: "Copy Originals To...", icon: "export", action: () => void copyToFlow(ids) },
    { label: "Show in Finder", icon: "folder", action: () => void api(`/media/${item.id}/reveal`, { method: "POST" }) },
    { label: "Edit With...", icon: "external", action: () => void openWithFlow(item.id) },
  ];
  if (item.stack_id) {
    entries.push(
      { label: "Open Stack", icon: "stack", action: () => navigate(specHash({ rules: [{ field: "stack", value: item.stack_id }], expand_stacks: true, title: "Stack" } as QuerySpec)) },
      { label: "Unstack", icon: "layers", action: async () => { await api(`/stacks/${item.stack_id}`, { method: "DELETE" }); invalidateMedia(); } },
      { label: "Make Stack Top", icon: "stack", action: async () => { await api(`/stacks/${item.stack_id}/top`, { method: "POST", body: JSON.stringify({ media_id: item.id }) }); invalidateMedia(); toast("Stack top set"); } },
      { label: "Remove from Stack", icon: "minus", action: async () => { await api(`/stacks/${item.stack_id}/remove`, { method: "POST", body: JSON.stringify({ ids }) }); invalidateMedia(); } },
    );
  } else if (ids.length > 1) {
    entries.push({ label: "Stack", icon: "stack", action: () => void stackFlow(ids) });
  }
  return entries;
}

let registered = false;

export function registerOrganize(): void {
  if (registered) return;
  registered = true;
  tileHooks.ctx.push(tileEntries);
  selectbarExtras.push(
    { label: "Keywords", icon: "tag", handler: (ids) => assignKeywordsFlow(ids) },
    { label: "Rate", icon: "star", handler: (ids) => {
      const bar = document.querySelector<HTMLElement>(".sel-bar");
      const rect = bar?.getBoundingClientRect();
      openContextMenu(rect ? rect.left + 80 : 200, rect ? rect.top - 230 : 200, [0, 1, 2, 3, 4, 5].map((n) => ({
        label: n === 0 ? "No rating" : "★".repeat(n), action: () => void saveMeta(ids, { rating: n }),
      })));
    } },
    { label: "Stack", icon: "stack", handler: (ids) => { if (ids.length > 1) void stackFlow(ids); } },
    { label: "Rename", icon: "rename", handler: (ids) => renameFlow(ids) },
  );
  window.addEventListener("keydown", (event) => {
    if (state.viewer || state.selection.size === 0) return;
    if (document.querySelector(".modal-backdrop")) return;
    if (ratingKey(event, selectionIds())) {
      event.preventDefault();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      assignKeywordsFlow(selectionIds());
      return;
    }
    const target = event.target as HTMLElement | null;
    if (event.metaKey || event.ctrlKey || event.altKey || (target && target.closest("input, textarea, select"))) return;
    const hit = keywordState.list.find((k) => k.shortcut && k.shortcut === event.key.toLowerCase());
    if (hit) {
      event.preventDefault();
      void api("/media/keywords", { method: "POST", body: JSON.stringify({ ids: selectionIds(), add: [hit.id] }) })
        .then(() => { toast(`Tagged ${countFmt(state.selection.size)} with ${hit.name}`); void loadKeywords(); });
    }
  });
  window.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openKeywordManager();
    }
  });
}

export { specKey };
