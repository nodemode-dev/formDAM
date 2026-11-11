import { api } from "../../engine/api.js";
import { countFmt, humanBytes } from "../../engine/format.js";
import { invalidateMedia, loadDedupSets, on, pollJob, refreshSummary, state } from "../../engine/store.js";
import type { DupSet, Media } from "../../engine/types.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { toast } from "../toast.js";
import { loadThumb } from "./grid.js";

function cell(item: Media, tag: string | null, sim: number | null): HTMLElement {
  const img = h("img", { alt: item.name, loading: "lazy" }) as HTMLImageElement;
  loadThumb(img, item.id, 384);
  const shot = h("div", { class: "dup-shot" }, img);
  if (tag) shot.append(h("span", { class: "dup-tag" }, tag));
  const meta = h(
    "div",
    { class: "dup-meta" },
    h("div", {}, item.name),
    h("div", {}, `${item.width ?? "?"} x ${item.height ?? "?"} · ${humanBytes(item.size)}`),
  );
  if (sim !== null) meta.append(h("div", { class: "dup-pct" }, `${sim}% match`));
  return h("div", { class: "dup-cell" }, shot, meta);
}

function refreshAfterChange(): void {
  invalidateMedia();
  void loadDedupSets();
  void refreshSummary();
}

async function guarded(action: () => Promise<void>): Promise<void> {
  try {
    await action();
  } catch (err) {
    toast(String((err as Error).message), "error");
    void loadDedupSets().catch(() => undefined);
  }
}

export function mountDedupPage(host: HTMLElement): () => void {
  const slider = h("input", { type: "range", min: "58", max: "100", step: "1", value: "94" }) as HTMLInputElement;
  const sliderVal = h("span", { style: "font-variant-numeric:tabular-nums;color:var(--text-muted)" }, "94");
  slider.addEventListener("input", () => (sliderVal.textContent = slider.value));
  const scanBtn = h("button", { class: "btn primary", type: "button" }, iconEl("refresh"), "Scan Library") as HTMLButtonElement;
  const exactBtn = h("button", { class: "btn", type: "button" }, "Resolve all exact") as HTMLButtonElement;
  const videosCheck = h("input", { type: "checkbox", checked: true }) as HTMLInputElement;
  videosCheck.checked = true;
  const autoExactCheck = h("input", { type: "checkbox" }) as HTMLInputElement;
  let kindFilter: "all" | "exact" | "visual" = "all";
  const chips = h("div", { class: "chip-row" });
  (["all", "exact", "visual"] as const).forEach((kind) => {
    const chip = h("button", { type: "button" }, kind === "all" ? "All" : kind === "exact" ? "Exact" : "Visual");
    chip.dataset.kind = kind;
    chip.addEventListener("click", () => {
      kindFilter = kind;
      chips.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.kind === kind));
      render();
    });
    chips.append(chip);
  });
  chips.querySelector("button")!.classList.add("active");
  const totals = h("span", { class: "topbar-sub" }, "");
  const status = h("p", { style: "margin:0 0 16px;color:var(--text-faint);font-size:12.5px" },
    "Powered by the deduplakit visual engine: exact byte matches plus perceptual matching across photos & videos. Resolving keeps the best copy & moves the rest to Recently Deleted.");
  const setsWrap = h("div", {});
  const pad = h(
    "div",
    { class: "view-pad" },
    h("div", { class: "section-head" },
      h("h2", {}, "Duplicates"),
      totals,
      h("span", { class: "head-spacer" }),
      chips,
      h("span", { class: "zoom-wrap" }, iconEl("sliders"), slider, sliderVal),
      exactBtn,
      scanBtn,
    ),
    h("div", { style: "display:flex;gap:20px;margin:0 0 12px" },
      h("label", { class: "field-check" }, videosCheck, "Include videos"),
      h("label", { class: "field-check" }, autoExactCheck, "Auto-resolve exact sets during scan"),
    ),
    status,
    setsWrap,
  );
  host.append(pad);

  function renderSet(set: DupSet): HTMLElement {
    const resolveBtn = h("button", { class: "btn", type: "button" }, iconEl("check"), "Keep best, trash the rest");
    resolveBtn.addEventListener("click", () => void guarded(async () => {
      const res = await api<{ trashed: number }>(`/dedup/sets/${set.id}/resolve`, { method: "POST", body: JSON.stringify({}) });
      toast(`Moved ${countFmt(res.trashed)} to Recently Deleted`);
      refreshAfterChange();
    }));

    function memberCell(item: typeof set.keeper, isKeeper: boolean): HTMLElement {
      const node = cell(item, isKeeper ? "Keeper" : null, isKeeper ? null : (item.pair_sim ?? set.similarity));
      if (!isKeeper) {
        const actions = h("div", { style: "display:flex;gap:6px;margin-top:6px" });
        const keepThis = h("button", { class: "btn", type: "button", style: "padding:3px 10px;font-size:11.5px" }, "Keep this one");
        keepThis.addEventListener("click", () => void guarded(async () => {
          const res = await api<{ trashed: number }>(`/dedup/sets/${set.id}/resolve`, {
            method: "POST", body: JSON.stringify({ keep_media_id: item.id }),
          });
          toast(`Kept ${item.name}; moved ${countFmt(res.trashed)} to Recently Deleted`);
          refreshAfterChange();
        }));
        const trashOne = h("button", { class: "btn danger", type: "button", style: "padding:3px 10px;font-size:11.5px" }, "Trash");
        trashOne.addEventListener("click", () => void guarded(async () => {
          await api(`/dedup/sets/${set.id}/members/${item.id}/trash`, { method: "POST" });
          refreshAfterChange();
        }));
        actions.append(keepThis, trashOne);
        node.append(actions);
      }
      return node;
    }

    const pair = h(
      "div",
      { class: "dup-pair" },
      memberCell(set.keeper, true),
      ...set.members.map((m) => memberCell(m, false)),
    );
    return h(
      "div",
      { class: "dup-set glass-panel" },
      h("div", { class: "dup-set-head" },
        h("span", { class: "dup-kind" }, set.match_kind === "exact" ? "Exact duplicates" : "Visually identical"),
        h("span", { class: "dup-sim" }, set.match_kind === "exact" ? "byte-for-byte" : `weakest member ${set.similarity}%`),
        h("span", { class: "head-spacer", style: "flex:1" }),
        resolveBtn,
      ),
      pair,
    );
  }

  function render(): void {
    const all = state.dedupSets;
    const sets = kindFilter === "all" ? all : all.filter((s) => s.match_kind === kindFilter);
    exactBtn.disabled = !all.some((s) => s.match_kind === "exact");
    const reclaimable = all.reduce((sum, s) => sum + ((s as { reclaimable?: number }).reclaimable ?? 0), 0);
    totals.textContent = all.length ? `${countFmt(all.length)} sets · ${humanBytes(reclaimable)} reclaimable` : "";
    if (sets.length === 0) {
      setsWrap.replaceChildren(
        h("div", { class: "empty-center" },
          h("div", { class: "empty-card glass-panel" },
            iconEl("dupes"),
            h("span", { class: "empty-title" }, "No duplicate sets"),
            h("span", { class: "empty-sub" }, "Run a scan to fingerprint the whole library. Private & hidden items are never scanned."),
          )),
      );
      return;
    }
    setsWrap.replaceChildren(...sets.map(renderSet));
  }

  scanBtn.addEventListener("click", async () => {
    scanBtn.disabled = true;
    try {
      const res = await api<{ job_id: string }>("/dedup/scan", {
        method: "POST",
        body: JSON.stringify({
          threshold: Number(slider.value),
          include_videos: videosCheck.checked,
          auto_resolve_exact: autoExactCheck.checked,
        }),
      });
      toast("Duplicate scan started");
      pollJob(res.job_id, (job) => {
        scanBtn.disabled = false;
        if (job.phase === "error") toast(job.error, "error");
        else {
          const skipped = job.counts.videos_skipped ?? 0;
          toast(`Found ${countFmt((job.counts.exact_sets ?? 0) + (job.counts.visual_sets ?? 0))} sets${skipped ? ` · ${countFmt(skipped)} videos skipped (ffmpeg missing)` : ""}`);
        }
        void loadDedupSets();
        void refreshSummary();
      });
    } catch (err) {
      scanBtn.disabled = false;
      toast(String((err as Error).message), "error");
    }
  });

  exactBtn.addEventListener("click", () => void guarded(async () => {
    const res = await api<{ trashed: number }>("/dedup/resolve-exact", { method: "POST" });
    toast(`Moved ${countFmt(res.trashed)} exact copies to Recently Deleted`);
    refreshAfterChange();
  }));

  const off = on("dedup", render);
  render();
  void loadDedupSets();
  return off;
}
