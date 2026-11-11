import { api, apiUpload } from "../../engine/api.js";
import { countFmt, humanBytes } from "../../engine/format.js";
import { invalidateMedia, loadAlbums, navigate, pollJob, refreshSummary, state } from "../../engine/store.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { openModal } from "../modal.js";
import { promptText } from "../prompt.js";
import { toast } from "../toast.js";
import { loadImage } from "./grid.js";
import { pickFolder } from "./outputs.js";
import { openPackageFlow } from "./packages.js";

interface LibraryEntry { path: string; name: string; active: boolean; exists: boolean; opened_ts?: number }
interface RepairReport { integrity: string; finished?: number; deep: boolean; counts: Record<string, number>; missing: Array<{ name: string; path: string }>; offline: Array<{ name: string; path: string }>; orphans: string[] }
interface LibraryInfo { path: string; name: string; items: number; bytes: number; referenced: number; libraries: LibraryEntry[]; repair: RepairReport | null }
interface DiskFile { name: string; path: string; size: number; mtime: number; kind: string; media_id: number | null; rating: number; label: string }
const DISK_LABEL_KEYS: Record<string, string> = { "6": "red", "7": "yellow", "8": "green", "9": "blue" };

function paintDiskMeta(node: HTMLElement, f: DiskFile): void {
  const stars = node.querySelector<HTMLElement>(".tile-stars");
  const dot = node.querySelector<HTMLElement>(".tile-label");
  if (stars) {
    setText(stars, f.rating > 0 ? "★".repeat(f.rating) : f.rating < 0 ? "Rejected" : "");
    stars.classList.toggle("hidden", f.rating === 0);
  }
  if (dot) {
    dot.className = `tile-label${f.label ? ` l-${f.label}` : " hidden"}`;
  }
}
interface DiskListing { path: string; parent: string | null; dirs: Array<{ name: string; path: string }>; files: DiskFile[]; shortcuts: Array<{ name: string; path: string }>; sidecars: number }

const MEDIA_EXT = new Set(["jpg", "jpeg", "png", "heic", "heif", "gif", "webp", "tif", "tiff", "bmp", "dng", "mov", "mp4", "m4v", "webm", "mkv", "3gp", "avi", "avif", "mts",
  "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf", "rw2", "rwl", "pef", "srw", "x3f", "3fr", "iiq", "erf", "kdc", "dcr", "mos", "mrw"]);

async function switchTo(path: string, create = false, name?: string): Promise<void> {
  try {
    await api("/library/switch", { method: "POST", body: JSON.stringify({ path, create, name }) });
    toast("Opening library...");
    location.hash = "#/library";
    location.reload();
  } catch (err) {
    toast(String((err as Error).message), "error");
  }
}

export function mountLibraryPage(host: HTMLElement): () => void {
  const title = h("h2", {}, "");
  const meta = h("span", { class: "topbar-sub" }, "");
  const list = h("div", { class: "list-rows" });
  const open = h("button", { class: "btn", type: "button" }, iconEl("folder"), "Open Library...");
  const create = h("button", { class: "btn primary", type: "button" }, iconEl("plus"), "New Library...");
  const deep = h("input", { type: "checkbox" }) as HTMLInputElement;
  const repairBtn = h("button", { class: "btn", type: "button" }, iconEl("refresh"), "Repair Library") as HTMLButtonElement;
  const report = h("div", { class: "repair-report" });
  const consolidateBtn = h("button", { class: "btn", type: "button" }, "Copy Referenced Files into Library") as HTMLButtonElement;
  const refNote = h("span", { class: "field-hint" }, "");
  host.append(h("div", { class: "view-pad lib-page" },
    h("div", { class: "section-head" }, title, meta, h("span", { class: "head-spacer" }), open, create),
    h("div", { class: "ed-sec-title" }, "Libraries"), list,
    h("div", { class: "ed-sec-title" }, "Maintenance"),
    h("div", { class: "row-gap" }, repairBtn, h("label", { class: "field-check" }, deep, "Verify every file's checksum (slow)")),
    report,
    h("div", { class: "ed-sec-title" }, "Referenced Files"),
    h("div", { class: "row-gap" }, consolidateBtn, refNote)));

  const load = async () => {
    const info = await api<LibraryInfo>("/library");
    setText(title, info.name);
    setText(meta, `${info.path} · ${countFmt(info.items)} items · ${humanBytes(info.bytes)}`);
    setText(refNote, info.referenced ? `${countFmt(info.referenced)} items are referenced in place and stay outside the library folder.` : "No referenced items; every original lives inside the library.");
    consolidateBtn.disabled = !info.referenced;
    patchList(list, info.libraries, (l) => l.path, (l) => {
      const sw = h("button", { class: "btn", type: "button" }, "Open");
      sw.addEventListener("click", () => void switchTo(l.path));
      const forget = h("button", { class: "icon-btn", type: "button", "aria-label": "Remove from list" }, iconEl("close"));
      forget.addEventListener("click", async () => {
        await api("/library/forget", { method: "POST", body: JSON.stringify({ path: l.path }) }).catch((err) => toast(String((err as Error).message), "error"));
        void load();
      });
      const row = h("div", { class: "list-row glass-panel" }, iconEl(l.active ? "check" : "library"),
        h("div", { class: "list-main" }, h("div", { class: "list-title" }, l.name), h("div", { class: "field-hint" }, l.path)), sw, forget);
      sw.classList.toggle("hidden", l.active);
      forget.classList.toggle("hidden", l.active);
      return row;
    });
    paintReport(info.repair);
  };

  function paintReport(r: RepairReport | null): void {
    if (!r) {
      report.replaceChildren(h("span", { class: "field-hint" }, "Repair checks the catalog, finds missing or offline originals, rebuilds missing thumbnails, lists files in the library folder that the catalog does not know, and clears stale caches."));
      return;
    }
    const c = r.counts ?? {};
    const lines = [
      `Catalog integrity: ${r.integrity}`,
      `${countFmt(c.checked ?? 0)} checked · ${countFmt(c.missing ?? 0)} missing · ${countFmt(c.offline ?? 0)} offline (referenced) · ${countFmt(c.thumbs_rebuilt ?? 0)} thumbnails rebuilt · ${countFmt(c.cache_freed ?? 0)} stale cache files removed${r.deep ? ` · ${countFmt(c.mismatched ?? 0)} checksum mismatches` : ""}`,
    ];
    const nodes: HTMLElement[] = lines.map((t) => h("div", {}, t));
    for (const m of [...(r.missing ?? []), ...(r.offline ?? [])].slice(0, 12)) nodes.push(h("div", { class: "field-hint" }, `${m.name}: ${m.path}`));
    if (r.orphans?.length) {
      const imp = h("button", { class: "btn", type: "button" }, `Import ${countFmt(r.orphans.length)} Unknown File${r.orphans.length === 1 ? "" : "s"}`);
      imp.addEventListener("click", async () => {
        const job = await api<{ job_id: string }>("/library/import-orphans", { method: "POST" });
        pollJob(job.job_id, (s) => { toast(`Imported ${countFmt(s.counts.imported ?? 0)}`); invalidateMedia(); void refreshSummary(); });
      });
      nodes.push(h("div", { class: "row-gap" }, h("span", {}, `${countFmt(r.orphans.length)} files in the library folder are not in the catalog.`), imp));
    }
    report.replaceChildren(...nodes);
  }

  repairBtn.addEventListener("click", async () => {
    repairBtn.disabled = true;
    const job = await api<{ job_id: string }>("/library/repair", { method: "POST", body: JSON.stringify({ deep: deep.checked }) });
    toast("Repairing...");
    pollJob(job.job_id, () => { repairBtn.disabled = false; toast("Repair finished"); void load(); });
  });
  consolidateBtn.addEventListener("click", async () => {
    consolidateBtn.disabled = true;
    const job = await api<{ job_id: string }>("/library/consolidate", { method: "POST", body: JSON.stringify({ ids: [] }) });
    pollJob(job.job_id, (s) => { toast(`Copied ${countFmt(s.counts.copied ?? 0)} into the library${s.counts.offline ? `, ${countFmt(s.counts.offline)} offline` : ""}`); void load(); });
  });
  open.addEventListener("click", async () => {
    const path = await pickFolder("Open Library");
    if (path) void switchTo(path);
  });
  create.addEventListener("click", async () => {
    const name = await promptText("New Library", "formDAM Library", "Name of the new library", "Choose Location...");
    if (!name) return;
    const path = await pickFolder("Where to create the library");
    if (path) void switchTo(path, true, name);
  });
  void load();
  return () => undefined;
}

export function mountDiskPage(host: HTMLElement, startPath: string): () => void {
  const crumbs = h("div", { class: "disk-crumbs" });
  const shortcuts = h("div", { class: "chip-list" });
  const dirs = h("div", { class: "chip-list disk-dirs" });
  const grid = h("div", { class: "tile-grid disk-grid" });
  const status = h("span", { class: "topbar-sub" }, "");
  const importLabel = h("span", {}, "Import Copies");
  const importBtn = h("button", { class: "btn primary", type: "button" }, iconEl("upload"), importLabel) as HTMLButtonElement;
  const refBtn = h("button", { class: "btn", type: "button" }, "Add in Place") as HTMLButtonElement;
  const allBtn = h("button", { class: "btn", type: "button" }, "Select All") as HTMLButtonElement;
  host.append(h("div", { class: "view-pad" }, h("div", { class: "row-gap" }, shortcuts), h("div", { class: "section-head" }, crumbs, status, h("span", { class: "head-spacer" }), allBtn, refBtn, importBtn), dirs, grid));
  const picked = new Set<string>();
  let listing: DiskListing | null = null;
  const sync = () => {
    importBtn.disabled = refBtn.disabled = picked.size === 0;
    setText(importLabel, picked.size ? `Import ${countFmt(picked.size)} Copies` : "Import Copies");
  };
  const go = (path: string) => navigate(`#/disk/${encodeURIComponent(path)}`);
  const load = async (path: string) => {
    try {
      listing = await api<DiskListing>(`/disk/browse?path=${encodeURIComponent(path)}`);
    } catch (err) {
      toast(String((err as Error).message), "error");
      return;
    }
    const data = listing;
    picked.clear();
    sync();
    const parts = data.path.split("/").filter(Boolean);
    const crumbNodes: HTMLElement[] = [];
    let acc = "";
    for (const part of parts.slice(-4)) {
      acc = data.path.slice(0, data.path.indexOf(part, acc.length) + part.length);
      const target = acc;
      const b = h("button", { class: "link-btn crumb", type: "button" }, part);
      b.addEventListener("click", () => go(target));
      crumbNodes.push(b, h("span", { class: "crumb-sep" }, "/"));
    }
    crumbNodes.pop();
    crumbs.replaceChildren(...crumbNodes);
    setText(status, `${countFmt(data.files.length)} media file${data.files.length === 1 ? "" : "s"}${data.sidecars ? ` · ${countFmt(data.sidecars)} XMP sidecars` : ""}`);
    patchList(shortcuts, data.shortcuts, (s) => s.path, (s) => {
      const c = h("button", { class: "chip", type: "button" }, iconEl("drive"), s.name);
      c.addEventListener("click", () => go(s.path));
      return c;
    });
    const dirItems = [...(data.parent ? [{ name: "..", path: data.parent }] : []), ...data.dirs];
    patchList(dirs, dirItems, (d) => d.path, (d) => {
      const c = h("button", { class: "chip big", type: "button" }, iconEl(d.name === ".." ? "back" : "folder"), d.name === ".." ? "Up" : d.name);
      c.addEventListener("click", () => go(d.path));
      return c;
    });
    patchList(grid, data.files, (f) => f.path, (f) => {
      const img = h("img", { alt: f.name, loading: "lazy", draggable: false }) as HTMLImageElement;
      loadImage(img, `/api/disk/thumb?path=${encodeURIComponent(f.path)}&s=384`);
      const badge = h("span", { class: `tile-chip disk-in${f.media_id ? "" : " hidden"}` }, "IN LIBRARY");
      const tile = h("div", { class: "tile disk-tile" }, img, h("div", { class: "tile-meta" }, h("span", { class: "tile-stars" }), h("span", { class: "tile-label" }), badge), h("div", { class: "disk-name" }, f.name));
      paintDiskMeta(tile, f);
      tile.addEventListener("click", (event) => {
        if (event.detail > 1) return;
        if (picked.has(f.path)) picked.delete(f.path);
        else picked.add(f.path);
        tile.classList.toggle("selected", picked.has(f.path));
        sync();
      });
      tile.addEventListener("dblclick", () => quickLook(f));
      return tile;
    }, (node, f) => {
      node.querySelector(".disk-in")?.classList.toggle("hidden", !f.media_id);
      node.classList.remove("selected");
      paintDiskMeta(node, f);
    });
  };
  const run = async (reference: boolean) => {
    const paths = [...picked];
    if (!paths.length) return;
    const job = await api<{ job_id: string }>("/import", { method: "POST", body: JSON.stringify({ path: paths[0], paths, reference }) });
    toast(`${reference ? "Adding" : "Importing"} ${countFmt(paths.length)}...`);
    pollJob(job.job_id, (s) => {
      toast(`${reference ? "Added in place" : "Imported"} ${countFmt(s.counts.imported ?? 0)} · ${countFmt(s.counts.duplicates ?? 0)} already in the library`);
      invalidateMedia();
      void refreshSummary();
      if (listing) void load(listing.path);
    });
  };
  importBtn.addEventListener("click", () => void run(false));
  refBtn.addEventListener("click", () => void run(true));
  allBtn.addEventListener("click", () => {
    if (!listing) return;
    const all = picked.size < listing.files.length;
    picked.clear();
    if (all) listing.files.forEach((f) => picked.add(f.path));
    grid.querySelectorAll<HTMLElement>(".disk-tile").forEach((t, i) => t.classList.toggle("selected", all && Boolean(listing?.files[i])));
    sync();
  });
  const keys = (event: KeyboardEvent) => {
    if (!picked.size || !listing || document.querySelector(".modal-backdrop")) return;
    const target = event.target as HTMLElement | null;
    if (event.metaKey || event.ctrlKey || event.altKey || (target && target.closest("input, textarea, select"))) return;
    const body: Record<string, unknown> = { paths: [...picked] };
    if (/^[0-5]$/.test(event.key)) body.rating = Number(event.key);
    else if (DISK_LABEL_KEYS[event.key]) {
      const label = DISK_LABEL_KEYS[event.key];
      body.label = listing.files.every((f) => !picked.has(f.path) || f.label === label) ? "" : label;
    }
    else if (event.key.toLowerCase() === "x") body.rating = -1;
    else return;
    event.preventDefault();
    const data = listing;
    void api("/disk/meta", { method: "POST", body: JSON.stringify(body) }).then(() => {
      for (const f of data.files) {
        if (!picked.has(f.path)) continue;
        if ("rating" in body) f.rating = body.rating as number;
        if ("label" in body) f.label = String(body.label);
      }
      grid.querySelectorAll<HTMLElement>(".disk-tile").forEach((node, i) => { const f = data.files[i]; if (f && picked.has(f.path)) paintDiskMeta(node, f); });
      toast(`Wrote XMP for ${countFmt(picked.size)} file${picked.size === 1 ? "" : "s"}`);
    }).catch((err) => toast(String((err as Error).message), "error"));
  };
  window.addEventListener("keydown", keys);
  void load(startPath || "~");
  return () => window.removeEventListener("keydown", keys);
}

function quickLook(f: DiskFile): void {
  const modal = openModal(f.name, 900);
  const src = `/api/disk/file?path=${encodeURIComponent(f.path)}`;
  const media = f.kind === "video"
    ? h("video", { src, controls: true, autoplay: true, class: "quicklook" })
    : h("img", { src, alt: f.name, class: "quicklook" });
  modal.body.append(media, h("div", { class: "field-hint" }, `${humanBytes(f.size)} · ${f.path}`));
}

async function collectEntries(items: DataTransferItemList): Promise<File[]> {
  const out: File[] = [];
  const walk = async (entry: FileSystemEntry | null): Promise<void> => {
    if (!entry) return;
    if (entry.isFile) {
      const file = await new Promise<File | null>((resolve) => (entry as FileSystemFileEntry).file(resolve, () => resolve(null)));
      if (file && MEDIA_EXT.has(file.name.split(".").pop()?.toLowerCase() ?? "")) out.push(file);
      return;
    }
    if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((resolve) => reader.readEntries(resolve, () => resolve([])));
        if (!batch.length) break;
        for (const child of batch) if (!child.name.startsWith(".")) await walk(child);
      }
    }
  };
  const entries = [...items].map((item) => (item.kind === "file" ? item.webkitGetAsEntry() : null));
  for (const entry of entries) await walk(entry);
  return out;
}

async function uploadAll(files: File[], albumId: number | null): Promise<void> {
  if (!files.length) {
    toast("Nothing to import: drop photos, videos or folders that contain them", "error");
    return;
  }
  toast(`Importing ${countFmt(files.length)} file${files.length === 1 ? "" : "s"}...`);
  const ids: number[] = [];
  let imported = 0;
  let failed = 0;
  for (let i = 0; i < files.length; i += 40) {
    const form = new FormData();
    const batch = files.slice(i, i + 40);
    for (const file of batch) form.append("files", file, file.name);
    try {
      const res = await apiUpload<{ counts: { imported: number }; ids: number[] }>("/import/upload", form);
      imported += res.counts.imported;
      ids.push(...(res.ids ?? []));
    } catch {
      failed += batch.length;
    }
  }
  if (failed) toast(`${countFmt(failed)} file${failed === 1 ? "" : "s"} could not be imported`, "error");
  if (albumId !== null && ids.length) {
    await api(`/albums/${albumId}/items`, { method: "POST", body: JSON.stringify({ media_ids: ids }) });
    void loadAlbums();
  }
  toast(`Imported ${countFmt(imported)}${albumId !== null ? ` and added ${countFmt(ids.length)} to the album` : ""}`);
  invalidateMedia();
  void refreshSummary();
}

function albumTarget(target: EventTarget | null): number | null {
  const el = target as HTMLElement | null;
  const row = el?.closest<HTMLElement>("[data-album-id]");
  if (row?.dataset.albumId) return Number(row.dataset.albumId);
  if (state.route.view === "album" && !el?.closest(".sidebar")) {
    const album = state.albums.find((a) => a.id === Number(state.route.param));
    if (album && !album.is_smart) return album.id;
  }
  return null;
}

let registered = false;

export function registerLibraryDrops(): void {
  if (registered) return;
  registered = true;
  let hover: HTMLElement | null = null;
  const mark = (el: HTMLElement | null) => {
    if (hover === el) return;
    hover?.classList.remove("drop-target");
    hover = el;
    hover?.classList.add("drop-target");
  };
  document.addEventListener("dragover", (event) => {
    const row = (event.target as HTMLElement | null)?.closest<HTMLElement>("[data-album-id]") ?? null;
    mark(row);
    if (row && event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });
  document.addEventListener("dragleave", (event) => {
    if (!(event.relatedTarget as HTMLElement | null)?.closest?.("[data-album-id]")) mark(null);
  });
  document.addEventListener("drop", (event) => {
    mark(null);
    const target = event.target as HTMLElement | null;
    if (target?.closest(".drop-zone") || !event.dataTransfer) return;
    const albumId = albumTarget(target);
    const internal = event.dataTransfer.getData("application/x-dam-ids");
    if (internal) {
      event.preventDefault();
      if (albumId === null) return;
      const ids = JSON.parse(internal) as number[];
      void api(`/albums/${albumId}/items`, { method: "POST", body: JSON.stringify({ media_ids: ids }) }).then(() => {
        toast(`Added ${countFmt(ids.length)} to ${state.albums.find((a) => a.id === albumId)?.name ?? "the album"}`);
        void loadAlbums();
      }).catch((err) => toast(String((err as Error).message), "error"));
      return;
    }
    if (!event.dataTransfer.items?.length) return;
    event.preventDefault();
    const dropped = [...event.dataTransfer.files];
    const zips = dropped.filter((f) => f.name.toLowerCase().endsWith(".zip"));
    for (const zip of zips) {
      void openPackageFlow(zip).then((ok) => { if (!ok) toast(`${zip.name} is not a formDAM share package`, "error"); });
    }
    if (zips.length && zips.length === dropped.length) return;
    void collectEntries(event.dataTransfer.items).then((files) => uploadAll(files, albumId));
  });
}
