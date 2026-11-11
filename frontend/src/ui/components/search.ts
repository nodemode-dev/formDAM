import { api } from "../../engine/api.js";
import { prefGet, prefSet } from "../../engine/prefstore.js";
import { countFmt } from "../../engine/format.js";
import { navigate, pollJob, specKey, type QuerySpec } from "../../engine/store.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { toast } from "../toast.js";
import { clipCard } from "./discover.js";
import { advancedFindFlow } from "./find.js";
import { mountGrid } from "./grid.js";
import { smartFromSpec, specHash } from "./organize.js";

const SCOPES: Array<{ key: string; label: string }> = [
  { key: "name", label: "Filenames" },
  { key: "title", label: "Titles" },
  { key: "caption", label: "Captions" },
  { key: "keywords", label: "Keywords" },
  { key: "ocr", label: "Text in image" },
  { key: "people", label: "People" },
  { key: "places", label: "Places" },
  { key: "dates", label: "Dates" },
  { key: "albums", label: "Albums" },
  { key: "camera", label: "Camera" },
  { key: "subjects", label: "Subjects" },
  { key: "visual", label: "Looks like" },
];

interface SuggestItem { label: string; count: number | null; rule: { field: string; op?: string; value?: unknown } }
interface SuggestGroup { kind: string; title: string; items: SuggestItem[] }

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
  const suggestions = h("div", { class: "suggest-groups" });
  const clip = clipCard(() => void run());
  const results = h("div", { class: "search-results" });
  const advanced = h("button", { class: "btn", type: "button" }, iconEl("sliders"), "Advanced Find");
  advanced.addEventListener("click", () => advancedFindFlow([{ field: "visual", value: query }]));
  const saveSmart = h("button", { class: "btn", type: "button" }, iconEl("smart"), "Save as Smart Album");
  saveSmart.addEventListener("click", () => void smartFromSpec(query, currentSpec()));
  const pad = h("div", { class: "view-pad search-head" },
    h("div", { class: "section-head" }, h("h2", {}, `Results for "${query}"`), sub, h("span", { class: "head-spacer" }), advanced, saveSmart),
    chips,
    suggestions,
    ocrCard,
    clip.el,
  );
  host.append(pad, results);
  let disposeGrid: (() => void) | null = null;

  function currentSpec(): QuerySpec {
    return { text: query, fields: [...scopes], title: `Results for "${query}"` } as QuerySpec;
  }

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
        h("span", { class: "settings-hint" }, "No text engine is available: the bundled model failed to load & tesseract is not installed. Rebuild the app, or brew install tesseract as a fallback, then reopen formDAM."));
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

  const empty = h("div", { class: "empty-center hidden" },
    h("div", { class: "empty-card glass-panel" },
      iconEl("search"),
      h("span", { class: "empty-title" }, "No matches"),
      h("span", { class: "empty-sub" }, "Adjust the scopes above, or run the text or visual scan if it is offered."),
    ));
  pad.append(empty);
  let seq = 0;
  let alive = true;
  let headReady: Promise<void> = Promise.resolve();

  async function run(): Promise<void> {
    if (!alive) return;
    const mine = ++seq;
    setText(sub, "Searching...");
    const spec = currentSpec();
    const [data] = await Promise.all([api<{ count: number }>(`/browse/count?spec=${encodeURIComponent(JSON.stringify(spec))}`), headReady]);
    if (mine !== seq || !alive) return;
    setText(sub, `${countFmt(data.count)} match${data.count === 1 ? "" : "es"} in ${[...scopes].map((k) => SCOPES.find((s) => s.key === k)?.label).join(", ")}`);
    empty.classList.toggle("hidden", data.count > 0);
    disposeGrid?.();
    results.replaceChildren();
    disposeGrid = data.count > 0 ? mountGrid(results, specKey(spec), false) : null;
  }

  async function suggest(): Promise<void> {
    const data = await api<{ groups: SuggestGroup[] }>(`/search/suggest?text=${encodeURIComponent(query)}`);
    patchList(suggestions, data.groups, (g) => g.kind, (g) => {
      const row = h("div", { class: "chip-list" });
      for (const item of g.items) {
        const chip = h("button", { class: "chip big", type: "button" }, h("span", { class: "chip-text" }, item.label),
          item.count !== null ? h("span", { class: "chip-count" }, countFmt(item.count)) : "");
        chip.addEventListener("click", () => navigate(specHash({ rules: [item.rule], title: item.label, expand_stacks: true } as QuerySpec)));
        row.append(chip);
      }
      return h("div", { class: "suggest-group" }, h("span", { class: "suggest-title" }, g.title), row);
    });
  }

  headReady = Promise.all([refreshOcrCard(), clip.refresh(), suggest()]).then(() => undefined, () => undefined);
  void run();
  return () => {
    alive = false;
    seq++;
    disposeGrid?.();
  };
}
