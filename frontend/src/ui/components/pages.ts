import { api } from "../../engine/api.js";
import { countFmt, fullStamp } from "../../engine/format.js";
import { keywordState, loadKeywords, navigate, on } from "../../engine/store.js";
import type { QuerySpec } from "../../engine/store.js";
import { h } from "../dom.js";
import { iconEl, type IconName } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { loadThumb } from "./grid.js";
import { openKeywordManager, specHash } from "./organize.js";

interface Batch {
  id: number;
  started_ts: number;
  source: string;
  label: string | null;
  count: number;
  covers: number[];
}

const SOURCE_LABEL: Record<string, string> = { folder: "Folder import", drop: "Dropped files", iphone: "iPhone import" };

export function coverCard(title: string, sub: string, covers: number[], hash: string): HTMLElement {
  const grid = h("div", { class: "month-covers" });
  for (const id of covers.slice(0, 4)) {
    const img = h("img", { alt: "", loading: "lazy", draggable: false }) as HTMLImageElement;
    loadThumb(img, id, 384);
    grid.append(img);
  }
  const card = h("div", { class: "month-card" }, grid, h("div", { class: "month-label" }, title), h("div", { class: "month-count" }, sub));
  card.addEventListener("click", () => navigate(hash));
  return card;
}

export function mountImportsPage(host: HTMLElement): () => void {
  const grid = h("div", { class: "month-grid" });
  const empty = h("div", { class: "empty-center hidden" }, h("div", { class: "empty-card glass-panel" }, iconEl("upload"),
    h("span", { class: "empty-title" }, "No imports yet"), h("span", { class: "empty-sub" }, "Each import appears here as a batch you can reopen.")));
  host.append(h("div", { class: "view-pad" }, grid, empty));
  void api<{ batches: Batch[] }>("/imports").then((res) => {
    empty.classList.toggle("hidden", res.batches.length > 0);
    patchList(grid, res.batches, (b) => String(b.id), (b) => coverCard(
      b.label || SOURCE_LABEL[b.source] || "Import",
      `${SOURCE_LABEL[b.source] ?? b.source} · ${fullStamp(b.started_ts)} · ${countFmt(b.count)} items`,
      b.covers,
      specHash({ rules: [{ field: "batch", value: b.id }], sort: "added", expand_stacks: true, title: b.label || "Import" } as QuerySpec),
    ));
  });
  return () => undefined;
}

export function mountKeywordsPage(host: HTMLElement): () => void {
  const manage = h("button", { class: "btn", type: "button" }, iconEl("tag"), "Keyword Manager");
  manage.addEventListener("click", openKeywordManager);
  const list = h("div", { class: "kw-browse" });
  host.append(h("div", { class: "view-pad" }, h("div", { class: "section-head" }, h("h2", {}, "Keywords"), h("span", { class: "head-spacer" }), manage), list));
  const sync = () => patchList(list, keywordState.list.filter((k) => k.count > 0), (k) => String(k.id), (k) => {
    const btn = h("button", { class: "chip big", type: "button" }, h("span", { class: "chip-text" }, k.name), h("span", { class: "chip-count" }, countFmt(k.count)));
    btn.addEventListener("click", () => navigate(specHash({ rules: [{ field: "keyword", value: k.id }], title: k.name } as QuerySpec)));
    return btn;
  }, (node, k) => setText(node.querySelector(".chip-count") as HTMLElement, countFmt(k.count)));
  const off = on("keywords", sync);
  void loadKeywords();
  sync();
  return off;
}

interface MediaType {
  key: string;
  label: string;
  count: number;
  cover: number | null;
}

const TYPE_ICONS: Record<string, IconName> = {
  video: "video", live: "play", selfie: "person", portrait: "camera", panorama: "fit", slomo: "clock",
  burst: "stack", raw: "file", screenshot: "screenshot", screen_recording: "stage",
  timelapse: "clock", cinematic: "video", spatial: "cube", long_exposure: "wave", animated: "play",
};

export function mediaTypeCards(container: HTMLElement): () => void {
  let alive = true;
  const refresh = () => {
    void api<{ types: MediaType[] }>("/media-types").then((res) => {
      if (!alive) return;
      const shown = res.types.filter((t) => t.count > 0);
      patchList(container, shown, (t) => t.key, (t) => {
        const count = h("span", { class: "card-count" }, countFmt(t.count));
        const card = h("button", { class: "count-card glass-panel", type: "button" },
          iconEl(TYPE_ICONS[t.key] ?? "image"), h("span", { class: "card-label" }, t.label), count, h("span", { class: "row-tail" }, iconEl("chevron")));
        card.addEventListener("click", () => navigate(specHash({ rules: [{ field: "flag", value: t.key }], expand_stacks: t.key === "burst", title: t.label } as QuerySpec)));
        return card;
      }, (node, t) => setText(node.querySelector(".card-count") as HTMLElement, countFmt(t.count)));
    });
  };
  refresh();
  const off = on("summary", refresh);
  return () => {
    alive = false;
    off();
  };
}
