import { api } from "../../engine/api.js";
import { countFmt } from "../../engine/format.js";
import { invalidateMedia, navigate, on, pollJob, state, type QuerySpec } from "../../engine/store.js";
import type { Media } from "../../engine/types.js";
import type { CtxEntry } from "../contextmenu.js";
import { h } from "../dom.js";
import { iconEl, type IconName } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { promptText } from "../prompt.js";
import { toast } from "../toast.js";
import { loadThumb, tileHooks } from "./grid.js";
import { specHash } from "./organize.js";
import { coverCard } from "./pages.js";

interface Pet { id: number; name: string | null; species: string; count: number; cover: number | null }
interface Label { label: string; count: number; cover: number | null }
interface ClipStatus { ready: boolean; missing: string[]; pending: number; indexed: number; job: { id: string } | null }

const CONTENT: Array<[string, string, IconName]> = [
  ["document", "Documents", "file"], ["receipt", "Receipts", "receipt"], ["handwriting", "Handwriting", "pen"],
  ["illustration", "Illustrations", "brush"], ["diagram", "Diagrams", "layers"], ["qr code", "QR Codes", "qr"],
  ["whiteboard", "Whiteboards", "doc"], ["menu", "Menus", "doc"], ["map", "Maps", "map"],
];

function items(n: number): string {
  return `${countFmt(n)} item${n === 1 ? "" : "s"}`;
}

function petName(p: Pet): string {
  return p.name || (p.species === "dog" ? "Dog" : p.species === "cat" ? "Cat" : "Pet");
}

function petHash(p: Pet): string {
  return specHash({ rules: [{ field: "pet", value: p.id }], title: petName(p), expand_stacks: true } as QuerySpec);
}

function labelHash(label: string, title: string): string {
  return specHash({ rules: [{ field: "subject", value: label }], title, expand_stacks: true } as QuerySpec);
}

export function clipCard(onDone?: () => void): { el: HTMLElement; refresh: () => Promise<void> } {
  const text = h("span", { class: "settings-hint" }, "");
  const btn = h("button", { class: "btn primary", type: "button" }, iconEl("sparkle"), "Index Now") as HTMLButtonElement;
  const el = h("div", { class: "ocr-card glass-panel hidden" }, iconEl("eye"), text, h("span", { class: "head-spacer" }), btn);
  async function refresh(): Promise<void> {
    const s = await api<ClipStatus>("/clip/status");
    const show = !s.ready || s.pending > 0;
    el.classList.toggle("hidden", !show);
    btn.classList.toggle("hidden", !s.ready || Boolean(s.job));
    if (!s.ready) setText(text, "Visual search needs its model; run the installer again to fetch it (CLIP ViT-B/32, about 150 MB).");
    else if (s.job) setText(text, `Indexing ${countFmt(s.pending)} items for visual search, pets & content...`);
    else setText(text, `${countFmt(s.pending)} items are not indexed for visual search yet.`);
    if (s.job) pollJob(s.job.id, () => { void refresh(); onDone?.(); });
  }
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const res = await api<{ job_id: string }>("/clip/index", { method: "POST" });
    btn.disabled = false;
    toast("Indexing for visual search...");
    pollJob(res.job_id, () => { void refresh(); onDone?.(); });
    void refresh();
  });
  return { el, refresh };
}

function petCard(p: Pet): HTMLElement {
  const img = h("img", { alt: "", draggable: false }) as HTMLImageElement;
  if (p.cover !== null) loadThumb(img, p.cover, 384);
  const name = h("span", { class: "pet-name" }, petName(p));
  const count = h("span", { class: "pet-count" }, items(p.count));
  const rename = h("button", { class: "link-btn", type: "button" }, "Name");
  rename.addEventListener("click", async (event) => {
    event.stopPropagation();
    const value = await promptText(`Name this ${p.species}`, p.name ?? "", "", "Save");
    if (value === null) return;
    await api(`/pets/${p.id}`, { method: "PATCH", body: JSON.stringify({ name: value }) });
    p.name = value.trim() || null;
    setText(name, petName(p));
  });
  const card = h("div", { class: "pet-card" }, h("div", { class: "pet-cover" }, img), h("div", { class: "pet-meta" }, name, rename), count);
  card.addEventListener("click", () => navigate(petHash(p)));
  return card;
}

export function mountPetsPage(host: HTMLElement): () => void {
  const grid = h("div", { class: "pet-grid" });
  const status = clipCard(() => void load());
  const empty = h("div", { class: "empty-center hidden" }, h("div", { class: "empty-card glass-panel" }, iconEl("paw"),
    h("span", { class: "empty-title" }, "No Pets Yet"), h("span", { class: "empty-sub" }, "Dogs and cats are recognised during visual indexing and grouped by animal.")));
  host.append(h("div", { class: "view-pad" }, status.el, grid, empty));
  let alive = true;
  async function load(): Promise<void> {
    const res = await api<{ pets: Pet[] }>("/pets");
    if (!alive) return;
    empty.classList.toggle("hidden", res.pets.length > 0);
    patchList(grid, res.pets, (p) => String(p.id), petCard, (node, p) => {
      setText(node.querySelector(".pet-count") as HTMLElement, items(p.count));
      setText(node.querySelector(".pet-name") as HTMLElement, petName(p));
    });
  }
  void status.refresh();
  void load();
  return () => {
    alive = false;
  };
}

export function mountSubjectsPage(host: HTMLElement): () => void {
  const grid = h("div", { class: "month-grid" });
  const content = h("div", { class: "month-grid" });
  const status = clipCard(() => void load());
  host.append(h("div", { class: "view-pad" }, status.el,
    h("div", { class: "section-head" }, h("h2", {}, "Content")), content,
    h("div", { class: "section-head" }, h("h2", {}, "Subjects")), grid));
  let alive = true;
  async function load(): Promise<void> {
    const [subjects, docs] = await Promise.all([api<{ labels: Label[] }>("/labels?kind=subject"), api<{ labels: Label[] }>("/labels?kind=content")]);
    if (!alive) return;
    const title = (l: string) => l.replace(/\b\w/g, (c) => c.toUpperCase());
    patchList(grid, subjects.labels, (l) => l.label, (l) => coverCard(title(l.label), items(l.count), l.cover !== null ? [l.cover] : [], labelHash(l.label, title(l.label))));
    patchList(content, docs.labels, (l) => l.label, (l) => coverCard(title(l.label), items(l.count), l.cover !== null ? [l.cover] : [], labelHash(l.label, title(l.label))));
  }
  void status.refresh();
  void load();
  return () => {
    alive = false;
  };
}

export function petsStrip(container: HTMLElement): () => void {
  const strip = h("div", { class: "strip" });
  const empty = h("div", { class: "empty-center hidden" }, h("div", { class: "empty-card glass-panel" }, iconEl("paw"),
    h("span", { class: "empty-title" }, "No Pets Yet"), h("span", { class: "empty-sub" }, "Dogs and cats appear here once visual indexing has run.")));
  container.append(strip, empty);
  let alive = true;
  const refresh = () => void api<{ pets: Pet[] }>("/pets").then((res) => {
    if (!alive) return;
    empty.classList.toggle("hidden", res.pets.length > 0);
    patchList(strip, res.pets, (p) => String(p.id), (p) => {
      const img = h("img", { alt: "", draggable: false }) as HTMLImageElement;
      if (p.cover !== null) loadThumb(img, p.cover, 384);
      const card = h("div", { class: "strip-card" }, h("div", { class: "strip-cover round" }, img), h("div", { class: "strip-label" }, petName(p)), h("div", { class: "strip-sub" }, items(p.count)));
      card.addEventListener("click", () => navigate(petHash(p)));
      return card;
    }, (node, p) => {
      setText(node.querySelector(".strip-label") as HTMLElement, petName(p));
      setText(node.querySelector(".strip-sub") as HTMLElement, items(p.count));
    });
  });
  refresh();
  const off = on("summary", refresh);
  return () => {
    alive = false;
    off();
  };
}

export function contentCards(container: HTMLElement): () => void {
  let alive = true;
  const refresh = () => void api<{ labels: Label[] }>("/labels?kind=content").then((res) => {
    if (!alive) return;
    const counts = new Map(res.labels.map((l) => [l.label, l.count]));
    const shown = CONTENT.filter(([key]) => counts.get(key));
    patchList(container, shown, ([key]) => key, ([key, label, icon]) => {
      const card = h("button", { class: "count-card glass-panel", type: "button" }, iconEl(icon), h("span", { class: "card-label" }, label),
        h("span", { class: "card-count" }, countFmt(counts.get(key) ?? 0)), h("span", { class: "row-tail" }, iconEl("chevron")));
      card.addEventListener("click", () => navigate(labelHash(key, label)));
      return card;
    }, (node, [key]) => setText(node.querySelector(".card-count") as HTMLElement, countFmt(counts.get(key) ?? 0)));
  });
  refresh();
  const off = on("summary", refresh);
  return () => {
    alive = false;
    off();
  };
}

function discoverEntries(item: Media): CtxEntry[] {
  const entries: CtxEntry[] = [
    { label: "Show Similar", icon: "compare", action: () => navigate(specHash({ rules: [{ field: "similar", value: item.id }], title: "Similar Items", expand_stacks: true } as QuerySpec)) },
  ];
  const pet = (item as Media & { pet_id?: number | null }).pet_id;
  if (pet) {
    entries.push({ label: "Not This Pet", icon: "paw", action: async () => {
      const ids = state.selection.has(item.id) && state.selection.size > 1 ? [...state.selection] : [item.id];
      await Promise.all(ids.map((id) => api(`/media/${id}/not-pet`, { method: "POST" })));
      invalidateMedia();
      toast("Removed from this pet");
    } });
  }
  return entries;
}

let registered = false;

export function registerDiscover(): void {
  if (registered) return;
  registered = true;
  tileHooks.ctx.push(discoverEntries);
}
