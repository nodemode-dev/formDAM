import { api, apiUpload } from "../../engine/api.js";
import { countFmt, formatDuration } from "../../engine/format.js";
import { invalidateMedia, pollJob, refreshSummary } from "../../engine/store.js";
import { h } from "../dom.js";
import { openModal } from "../modal.js";
import { iconEl } from "../icons.js";
import { toast } from "../toast.js";

export function mountImportPage(host: HTMLElement): () => void {
  const input = h("input", {
    class: "field-input",
    type: "text",
    placeholder: "/Users/you/Pictures/some-folder  (paste a folder or file path)", spellcheck: "false", autocomplete: "off", autocorrect: "off", autocapitalize: "off",
    style: "flex:1",
  }) as HTMLInputElement;
  const moveCheck = h("input", { type: "checkbox" }) as HTMLInputElement;
  const goBtn = h("button", { class: "btn primary", type: "button" }, iconEl("upload"), "Import") as HTMLButtonElement;
  const pickBtn = h("button", { class: "btn", type: "button" }, iconEl("folder"), "Choose Folder...") as HTMLButtonElement;
  const browseBtn = h("button", { class: "btn", type: "button" }, iconEl("drive"), "Browse") as HTMLButtonElement;

  pickBtn.addEventListener("click", async () => {
    pickBtn.disabled = true;
    try {
      const res = await api<{ path: string | null }>(`/fs/pick?initial=${encodeURIComponent(input.value.trim())}`, { method: "POST" });
      if (res.path) input.value = res.path;
    } catch (err) {
      toast(String((err as Error).message), "error");
    } finally {
      pickBtn.disabled = false;
    }
  });

  browseBtn.addEventListener("click", async () => {
    const modal = openModal("Browse for a folder", 520);
    const crumb = h("div", { class: "list-sub", style: "overflow-wrap:anywhere" }, "");
    const list = h("div", { class: "list-rows", style: "max-height:340px;overflow-y:auto" });
    const useBtn = h("button", { class: "btn primary", type: "button" }, "Import this folder");
    let current = "";

    async function show(path?: string): Promise<void> {
      if (!path) {
        const roots = await api<{ roots: Array<{ path: string; label: string; kind: string }> }>("/fs/roots");
        crumb.textContent = "Choose a starting point";
        list.replaceChildren(...roots.roots.map((root) => {
          const row = h("button", { class: "list-row glass-panel", type: "button" },
            iconEl(root.kind === "home" ? "home" : root.kind === "photos" ? "image" : "drive"),
            h("div", { class: "list-main" }, h("div", { class: "list-title" }, root.label),
              h("div", { class: "list-sub" }, root.path)));
          row.addEventListener("click", () => void show(root.path));
          return row;
        }));
        current = "";
        return;
      }
      const data = await api<{ path: string; parent: string | null; dirs: Array<{ name: string; path: string; is_pkg: boolean }> }>(
        `/fs/browse?path=${encodeURIComponent(path)}`,
      );
      current = data.path;
      crumb.textContent = data.path;
      const rows: HTMLElement[] = [];
      const up = h("button", { class: "list-row glass-panel", type: "button" },
        iconEl("back"), h("div", { class: "list-main" }, h("div", { class: "list-title" }, data.parent ? "Up one level" : "Starting points")));
      up.addEventListener("click", () => void show(data.parent ?? undefined));
      rows.push(up);
      for (const dir of data.dirs) {
        const row = h("button", { class: "list-row glass-panel", type: "button" },
          iconEl(dir.is_pkg ? "cube" : "folder"),
          h("div", { class: "list-main" }, h("div", { class: "list-title" }, dir.name)));
        row.addEventListener("click", () => void show(dir.path));
        rows.push(row);
      }
      list.replaceChildren(...rows);
    }

    useBtn.addEventListener("click", () => {
      if (current) input.value = current;
      modal.close();
    });
    modal.body.append(crumb, list, h("div", { class: "modal-actions" }, useBtn));
    void show();
  });
  const progress = h("div", { class: "banner glass-panel hidden" });

  async function run(): Promise<void> {
    const path = input.value.trim();
    if (!path) return;
    goBtn.disabled = true;
    try {
      const res = await api<{ job_id: string }>("/import", {
        method: "POST",
        body: JSON.stringify({ path, move: moveCheck.checked }),
      });
      progress.classList.remove("hidden");
      progress.replaceChildren(h("span", { class: "spin" }, iconEl("refresh")), h("span", { class: "banner-text" }, "Importing..."));
      pollJob(res.job_id, (job) => {
        goBtn.disabled = false;
        progress.classList.add("hidden");
        if (job.phase === "error") {
          toast(job.error, "error");
          return;
        }
        const c = job.counts;
        const verb = moveCheck.checked ? "Moved" : "Copied";
        toast(`${verb} ${countFmt(c.imported ?? 0)} into the library · ${countFmt(c.duplicates ?? 0)} exact duplicates skipped${moveCheck.checked ? "" : " · originals left in place"}`);
        invalidateMedia();
        void refreshSummary();
      });
    } catch (err) {
      goBtn.disabled = false;
      toast(String((err as Error).message), "error");
    }
  }


  const dropZone = h("div", { class: "drop-zone" },
    iconEl("upload"),
    h("div", { class: "drop-title" }, "Drop photos & videos here"),
    h("div", { class: "drop-sub" }, "Single files or a whole selection; every image & video type. Imports run through the same pipeline: sha-deduped, HEIC decoded, posters generated."));

  const MEDIA_DROP = new Set([
    "jpg", "jpeg", "png", "heic", "heif", "gif", "webp", "tif", "tiff", "bmp",
    "dng", "mov", "mp4", "m4v", "webm", "mkv", "3gp", "avi", "avif", "mts",
    "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf", "rw2", "rwl", "pef",
    "srw", "x3f", "3fr", "iiq", "erf", "kdc", "dcr", "mos", "mrw",
  ]);

  function mediaFiles(list: FileList | null): globalThis.File[] {
    if (!list) return [];
    return [...list].filter((file) => {
      const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
      return file.type.startsWith("image/") || file.type.startsWith("video/") || MEDIA_DROP.has(ext);
    });
  }

  async function uploadDropped(files: globalThis.File[]): Promise<void> {
    if (files.length === 0) {
      toast("Nothing droppable: only image & video files import", "error");
      return;
    }
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    progress.classList.remove("hidden");
    progress.replaceChildren(h("span", { class: "spin" }, iconEl("refresh")), h("span", { class: "banner-text" }, `Importing ${countFmt(files.length)} dropped file${files.length === 1 ? "" : "s"}...`));
    try {
      const res = await apiUpload<{ counts: { imported: number; duplicates: number; skipped: number; failed: number } }>("/import/upload", form);
      const c = res.counts;
      toast(`Imported ${countFmt(c.imported)} · ${countFmt(c.duplicates)} duplicates skipped${c.failed ? ` · ${countFmt(c.failed)} failed` : ""}`);
      invalidateMedia();
      void refreshSummary();
    } catch (err) {
      toast(String((err as Error).message), "error");
    } finally {
      progress.classList.add("hidden");
    }
  }

  let dragDepth = 0;
  const markDrag = (over: boolean) => dropZone.classList.toggle("drag-over", over);
  dropZone.addEventListener("dragenter", (event) => {
    event.preventDefault();
    dragDepth += 1;
    markDrag(true);
  });
  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });
  dropZone.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) markDrag(false);
  });
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dragDepth = 0;
    markDrag(false);
    void uploadDropped(mediaFiles(event.dataTransfer?.files ?? null));
  });

  const phoneList = h("div", { class: "list-rows" });
  const phoneHint = h("p", { class: "settings-hint" }, "Plug an iPhone or iPad in over USB & unlock it; it appears here on its own. First time: tap Trust This Computer on the device (iOS 26 may also ask to allow the wired connection).");
  const phoneStatus = h("p", { class: "settings-hint" }, "");
  const refreshBtn = h("button", { class: "btn", type: "button" }, iconEl("refresh"), "Refresh") as HTMLButtonElement;
  const phoneSection = h("div", { class: "phone-section hidden" },
    h("div", { class: "section-head" }, h("h2", {}, "From iPhone"), h("span", { class: "head-spacer" }), refreshBtn),
    phoneHint, phoneList);

  let phoneImporting = false;
  let phonePollBusy = false;
  let phoneTimer: number | null = null;
  let lastRoster = "";

  function setPhoneStatus(text: string): void {
    if (phoneStatus.textContent !== text) phoneStatus.textContent = text;
  }

  interface DeviceFile { key: number; name: string; size: number; kind: string; date: number | null; duration: number | null }

  const browseTitle = h("h3", { class: "phone-browse-title" }, "");
  const browseCount = h("span", { class: "phone-count" }, "");
  const selectAllBtn = h("button", { class: "btn", type: "button" }, "Select All") as HTMLButtonElement;
  const browseCloseBtn = h("button", { class: "btn", type: "button" }, iconEl("close")) as HTMLButtonElement;
  const deleteCheck = h("input", { type: "checkbox" }) as HTMLInputElement;
  const importSelBtn = h("button", { class: "btn primary", type: "button" }, iconEl("upload"), "Import Selected") as HTMLButtonElement;
  const importAllBtn = h("button", { class: "btn", type: "button" }, "Import All") as HTMLButtonElement;
  const browseGrid = h("div", { class: "phone-grid" });
  const browsePanel = h("div", { class: "phone-browse glass-panel hidden" },
    h("div", { class: "phone-browse-head" }, browseTitle, browseCount, h("span", { class: "head-spacer" }), selectAllBtn, browseCloseBtn),
    h("div", { class: "phone-browse-head" },
      h("label", { class: "field-check", style: "margin:0" }, deleteCheck, "Delete from the device after a safe import"),
      h("span", { class: "head-spacer" }), importAllBtn, importSelBtn),
    browseGrid);
  phoneSection.append(browsePanel, phoneStatus);

  let openSerial: string | null = null;
  let browseGen = 0;
  let browseFiles: DeviceFile[] = [];
  const selectedKeys = new Set<number>();
  let objectUrls: string[] = [];
  let thumbGenToken = 0;

  function syncBrowseButtons(): void {
    const n = selectedKeys.size;
    importSelBtn.replaceChildren(iconEl("upload"), `Import Selected${n ? ` (${countFmt(n)})` : ""}`);
    importSelBtn.disabled = phoneImporting || n === 0;
    importAllBtn.disabled = phoneImporting || browseFiles.length === 0;
    selectAllBtn.disabled = phoneImporting || browseFiles.length === 0;
    selectAllBtn.textContent = n === browseFiles.length && n > 0 ? "Select None" : "Select All";
    browseCloseBtn.disabled = phoneImporting;
  }

  function closeBrowse(sendClose: boolean): void {
    const serial = openSerial;
    openSerial = null;
    browsePanel.classList.add("hidden");
    browseGrid.replaceChildren();
    browseFiles = [];
    selectedKeys.clear();
    thumbGenToken += 1;
    for (const url of objectUrls) URL.revokeObjectURL(url);
    objectUrls = [];
    if (sendClose && serial) {
      void api("/idevice/session/close", { method: "POST", body: JSON.stringify({ serial }) }).catch(() => undefined);
    }
  }

  function pumpThumbs(serial: string, gen: number): void {
    const token = thumbGenToken;
    const queue = [...browseGrid.children] as HTMLElement[];
    let cursor = 0;
    let active = 0;
    const next = (): void => {
      if (token !== thumbGenToken) return;
      while (active < 4 && cursor < queue.length) {
        const tile = queue[cursor];
        cursor += 1;
        const img = tile.querySelector("img");
        if (!img) continue;
        active += 1;
        const key = tile.dataset.key;
        void fetch(`/api/idevice/thumb?serial=${encodeURIComponent(serial)}&key=${key}&gen=${gen}`, { headers: { "x-dam-local": "1" } })
          .then(async (res) => {
            if (!res.ok) throw new Error("no thumb");
            const url = URL.createObjectURL(await res.blob());
            if (token !== thumbGenToken) {
              URL.revokeObjectURL(url);
              return;
            }
            objectUrls.push(url);
            (img as HTMLImageElement).src = url;
            img.classList.add("ready");
          })
          .catch(() => tile.classList.add("no-thumb"))
          .finally(() => {
            active -= 1;
            next();
          });
      }
    };
    next();
  }

  function renderBrowse(): void {
    browseCount.textContent = `${countFmt(browseFiles.length)} item${browseFiles.length === 1 ? "" : "s"}`;
    browseGrid.replaceChildren(...browseFiles.map((file) => {
      const tile = h("button", { class: "ptile", type: "button", "data-key": String(file.key), title: file.name },
        h("img", { alt: file.name, draggable: "false" }),
        h("span", { class: "ptile-ph" }, iconEl(file.kind === "video" ? "video" : "image")),
        h("span", { class: "sel-dot" }, iconEl("check"))) as HTMLButtonElement;
      if (file.kind === "video" && file.duration) tile.append(h("span", { class: "ptile-dur" }, formatDuration(file.duration)));
      tile.addEventListener("click", () => {
        if (phoneImporting) return;
        if (selectedKeys.has(file.key)) {
          selectedKeys.delete(file.key);
          tile.classList.remove("selected");
        } else {
          selectedKeys.add(file.key);
          tile.classList.add("selected");
        }
        syncBrowseButtons();
      });
      return tile;
    }));
    syncBrowseButtons();
  }

  async function openBrowse(serial: string, name: string): Promise<void> {
    if (openSerial === serial) return;
    closeBrowse(openSerial !== null);
    openSerial = serial;
    browseTitle.textContent = name;
    browseCount.textContent = "";
    browsePanel.classList.remove("hidden");
    setPhoneStatus("Reading the photo catalog... keep the device unlocked.");
    try {
      const listing = await api<{ gen: number; files: DeviceFile[] }>("/idevice/contents", { method: "POST", body: JSON.stringify({ serial }) });
      if (openSerial !== serial) return;
      browseGen = listing.gen;
      browseFiles = listing.files;
      selectedKeys.clear();
      setPhoneStatus("");
      renderBrowse();
      pumpThumbs(serial, browseGen);
    } catch (err) {
      if (openSerial === serial) {
        closeBrowse(false);
        setPhoneStatus(String((err as Error).message));
      }
    }
  }

  function runDeviceImport(serial: string, keys: number[] | null, gen: number | null, after?: () => void): void {
    phoneImporting = true;
    syncBrowseButtons();
    void api<{ job_id: string }>("/idevice/import", {
      method: "POST",
      body: JSON.stringify({ serial, keys, gen, delete_after: deleteCheck.checked && gen !== null }),
    }).then((job) => {
      progress.classList.remove("hidden");
      progress.replaceChildren(h("span", { class: "spin" }, iconEl("refresh")), h("span", { class: "banner-text" }, "Importing from the device..."));
      pollJob(job.job_id, (done) => {
        phoneImporting = false;
        progress.classList.add("hidden");
        syncBrowseButtons();
        if (done.phase === "error") {
          toast(done.error ?? "Import failed; keep the device unlocked & trusted, then retry.", "error");
          setPhoneStatus(done.error ?? "");
          return;
        }
        const c = done.counts ?? {};
        const state = done as { deleted?: number; delete_error?: string };
        let note = `Imported ${countFmt(c.imported ?? 0)} from the device · ${countFmt(c.duplicates ?? 0)} already in the library`;
        if (state.deleted) note += ` · ${countFmt(state.deleted)} deleted from the device`;
        toast(note);
        if (state.delete_error) setPhoneStatus(`Device deletion failed: ${state.delete_error}`);
        invalidateMedia();
        void refreshSummary();
        if (after) after();
      });
    }).catch((err) => {
      phoneImporting = false;
      syncBrowseButtons();
      toast(String((err as Error).message), "error");
    });
  }

  selectAllBtn.addEventListener("click", () => {
    if (selectedKeys.size === browseFiles.length) {
      selectedKeys.clear();
      for (const tile of browseGrid.children) tile.classList.remove("selected");
    } else {
      for (const file of browseFiles) selectedKeys.add(file.key);
      for (const tile of browseGrid.children) tile.classList.add("selected");
    }
    syncBrowseButtons();
  });
  browseCloseBtn.addEventListener("click", () => closeBrowse(true));
  importSelBtn.addEventListener("click", () => {
    if (openSerial && selectedKeys.size) {
      const serial = openSerial;
      runDeviceImport(serial, [...selectedKeys], browseGen, () => {
        if (openSerial === serial && deleteCheck.checked) void reopenAfterImport(serial);
      });
    }
  });
  importAllBtn.addEventListener("click", () => {
    if (openSerial) {
      const serial = openSerial;
      runDeviceImport(serial, null, browseGen, () => {
        if (openSerial === serial && deleteCheck.checked) void reopenAfterImport(serial);
      });
    }
  });

  async function reopenAfterImport(serial: string): Promise<void> {
    const name = browseTitle.textContent ?? "";
    closeBrowse(false);
    await openBrowse(serial, name);
  }

  async function refreshDevices(manual = false): Promise<void> {
    if (phonePollBusy || phoneImporting) return;
    phonePollBusy = true;
    if (manual) refreshBtn.disabled = true;
    try {
      const res = await api<{ devices: Array<{ serial: string; name: string | null; state: string; via?: string }> }>("/idevice/devices");
      const roster = res.devices.map((dev) => `${dev.serial}|${dev.name}|${dev.state}|${dev.via ?? ""}`).join(";");
      if (roster === lastRoster && !manual) return;
      lastRoster = roster;
      setPhoneStatus(res.devices.length ? "" : "Watching for devices...");
      if (openSerial && !res.devices.some((dev) => dev.serial === openSerial && dev.state === "ready")) {
        closeBrowse(false);
        setPhoneStatus("The device went away; replug it & keep it unlocked.");
      }
      phoneList.replaceChildren(...res.devices.map((dev) => {
        const ready = dev.state === "ready";
        const name = dev.name ?? "iPhone (locked)";
        if (dev.via === "afc") {
          const importBtn = h("button", { class: "btn primary", type: "button" }, iconEl("upload"), "Import All") as HTMLButtonElement;
          importBtn.disabled = !ready || phoneImporting;
          importBtn.addEventListener("click", () => runDeviceImport(dev.serial, null, null));
          return h("div", { class: "list-row glass-panel" },
            iconEl("device"),
            h("div", { class: "list-main" },
              h("div", { class: "list-title" }, name),
              h("div", { class: "list-sub" }, ready ? "Ready to import (fallback path: whole roll)" : "Unlock the device & tap Trust This Computer")),
            importBtn);
        }
        const row = h(ready ? "button" : "div", { class: `list-row glass-panel${ready ? " row-click" : ""}`, ...(ready ? { type: "button" } : {}) },
          iconEl("device"),
          h("div", { class: "list-main" },
            h("div", { class: "list-title" }, name),
            h("div", { class: "list-sub" }, ready
              ? "Click to browse & import, like Photos"
              : "Unlock the device & tap Trust This Computer; iOS 26 may also ask you to allow the connection")),
          ready ? iconEl("chevron") : h("span", {}));
        if (ready) row.addEventListener("click", () => void openBrowse(dev.serial, name));
        return row;
      }));
      if (res.devices.length === 0) {
        phoneList.replaceChildren(h("div", { class: "empty-card glass-panel" },
          h("span", { class: "empty-title" }, "No device detected"),
          h("span", { class: "empty-sub" }, "Connect over USB & unlock the device; approve any prompt on it. Detection is automatic.")));
      }
    } catch (err) {
      setPhoneStatus(String((err as Error).message));
      if (manual) toast(String((err as Error).message), "error");
    } finally {
      phonePollBusy = false;
      if (manual) refreshBtn.disabled = false;
    }
  }
  refreshBtn.addEventListener("click", () => { lastRoster = "-"; void refreshDevices(true); });
  void api<{ supported: boolean; platform?: string; hint?: string }>("/idevice/status").then((res) => {
    if (res.supported) {
      phoneSection.classList.remove("hidden");
      if (res.hint) setPhoneStatus(res.hint);
      void refreshDevices(true);
      phoneTimer = window.setInterval(() => {
        if (!document.hidden) void refreshDevices();
      }, 3000);
    } else if (res.platform === "darwin") {
      phoneSection.classList.remove("hidden");
      refreshBtn.disabled = true;
      setPhoneStatus(res.hint || "iPhone import is unavailable in this engine build.");
    }
  }).catch(() => undefined);

  goBtn.addEventListener("click", run);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") void run();
  });

  const pad = h(
    "div",
    { class: "view-pad" },
    h("div", { class: "section-head" }, h("h2", {}, "Import")),
    h("p", { style: "margin:0 0 16px;color:var(--text-muted);font-size:13px;max-width:640px" },
      "By default files are COPIED into the managed library (originals/YYYY/MM inside the library folder shown in Settings) & your originals stay untouched where they are. Turn on Move to relocate them instead. Everything is SHA-256 fingerprinted & exact duplicates of anything already in the library are skipped."),
    h("div", { style: "display:flex;gap:12px;align-items:center;max-width:860px" }, input, pickBtn, browseBtn, goBtn),
    h("label", { class: "field-check", style: "margin-top:12px" }, moveCheck, "Move files into the library instead of copying"),
    h("div", { style: "margin-top:18px" }, dropZone),
    h("div", { style: "margin-top:16px" }, progress),
  );
  pad.append(phoneSection);
  host.append(pad);
  input.focus();
  return () => {
    if (phoneTimer !== null) window.clearInterval(phoneTimer);
    if (!phoneImporting) closeBrowse(true);
  };
}
