import { api } from "../../engine/api.js";
import { prefGet, prefSet } from "../../engine/prefstore.js";
import { countFmt } from "../../engine/format.js";
import { pollJob, state } from "../../engine/store.js";
import type { Media } from "../../engine/types.js";
import { h } from "../dom.js";
import { bindTileSize } from "../zoomctl.js";
import { iconEl } from "../icons.js";
import { toast } from "../toast.js";
import { bindSelectionClasses, tileFor } from "./grid.js";

const SCOPES: Array<{ key: string; label: string }> = [
  { key: "name", label: "Filenames" },
  { key: "ocr", label: "Text in image" },
  { key: "people", label: "People" },
  { key: "albums", label: "Albums" },
];

function loadScopes(): Set<string> {
  try {
    const raw = JSON.stringify(prefGet<string[]>("searchScopes", []));
    const parsed = raw ? (JSON.parse(raw) as string[]) : null;
    const set = new Set(parsed && parsed.length ? parsed : SCOPES.map((s) => s.key));
    return set;
  } catch {
    return new Set(SCOPES.map((s) => s.key));
  }
}

export function mountSearchPage(host: HTMLElement, query: string): () => void {
  const scopes = loadScopes();
  const sub = h("span", { class: "topbar-sub" }, "Searching...");
  const chips = h("div", { class: "scope-chips chip-row" });
  const ocrCard = h("div", { class: "ocr-card glass-panel" });
  ocrCard.style.display = "none";
  const grid = h("div", { class: "tile-grid" });
  const unbindTiles = bindTileSize(grid);
  const unbindSel = bindSelectionClasses(grid);
  const pad = h("div", { class: "view-pad" },
    h("div", { class: "section-head" }, h("h2", {}, `Results for "${query}"`), sub),
    chips,
    ocrCard,
    grid,
  );
  host.append(pad);
  let items: Media[] = [];

  for (const scope of SCOPES) {
    const chip = h("button", { type: "button" }, scope.label);
    chip.classList.toggle("active", scopes.has(scope.key));
    chip.addEventListener("click", () => {
      if (scopes.has(scope.key)) {
        if (scopes.size === 1) return;
        scopes.delete(scope.key);
      } else {
        scopes.add(scope.key);
      }
      chip.classList.toggle("active", scopes.has(scope.key));
      prefSet("searchScopes", [...scopes]);
      void run();
    });
    chips.append(chip);
  }

  async function refreshOcrCard(): Promise<void> {
    if (!scopes.has("ocr")) {
      ocrCard.style.display = "none";
      return;
    }
    ocrCard.style.display = "";
    const status = await api<{ engine: string | null; pending: number; job: { id: string } | null }>("/ocr/status");
    if (!status.engine) {
      ocrCard.replaceChildren(iconEl("type"),
        h("span", { class: "settings-hint" }, "No text engine is available: the bundled model failed to load & tesseract is not installed. Rebuild the app, or brew install tesseract as a fallback, then reopen DAM."));
      return;
    }
    const engineLabel = status.engine === "rapidocr" ? "RapidOCR (bundled, offline)" : "tesseract (fallback)";
    const force = status.pending === 0;
    const scanBtn = h("button", { class: "btn primary", type: "button" }, iconEl("sparkle"),
      force ? "Rescan all text" : `Scan text in ${countFmt(status.pending)} items`) as HTMLButtonElement;
    scanBtn.addEventListener("click", async () => {
      scanBtn.disabled = true;
      try {
        const res = await api<{ job_id: string }>("/ocr/scan", { method: "POST", body: JSON.stringify({ force }) });
        toast(force ? "Rescanning every item w/ the text model..." : "Scanning...");
        pollJob(res.job_id, (job) => {
          scanBtn.disabled = false;
          toast(job.phase === "done" ? "Text scan complete; searching again" : `Text scan ${job.phase}`);
          void refreshOcrCard();
          void run();
        });
      } catch (err) {
        scanBtn.disabled = false;
        toast(String((err as Error).message), "error");
      }
    });
    ocrCard.replaceChildren(iconEl("type"),
      h("span", { class: "settings-hint" }, `Engine: ${engineLabel}${force ? " · every item has been scanned; rescan re-reads them all" : " · some items have no extracted text yet"}`),
      h("span", { class: "head-spacer" }), scanBtn);
  }

  async function run(): Promise<void> {
    sub.textContent = "Searching...";
    const fields = [...scopes].join(",");
    const data = await api<{ items: Media[] }>(`/media/search?q=${encodeURIComponent(query)}&fields=${encodeURIComponent(fields)}`);
    items = data.items;
    for (const item of items) state.byId.set(item.id, item);
    sub.textContent = `${countFmt(items.length)} matches in ${[...scopes].map((k) => SCOPES.find((s) => s.key === k)?.label).join(", ")}`;
    if (items.length === 0) {
      grid.replaceChildren(
        h("div", { class: "empty-center", style: "grid-column:1/-1" },
          h("div", { class: "empty-card glass-panel" },
            iconEl("search"),
            h("span", { class: "empty-title" }, "No matches"),
            h("span", { class: "empty-sub" }, "Adjust the scopes above, or run the text scan if it is offered."),
          )),
      );
      return;
    }
    grid.replaceChildren(...items.map((item) => tileFor(item, () => items.map((m) => m.id), false)));
  }

  void refreshOcrCard();
  void run();
  return () => {
    unbindTiles();
    unbindSel();
  };
}
