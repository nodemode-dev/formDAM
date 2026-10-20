import { clearVaultToken, api } from "../../engine/api.js";
import { invalidateMedia, refreshSummary, state } from "../../engine/store.js";
import type { Media } from "../../engine/types.js";
import { h } from "../dom.js";
import { bindTileSize } from "../zoomctl.js";
import { iconEl } from "../icons.js";
import { toast } from "../toast.js";
import { bindSelectionClasses, tileFor } from "./grid.js";
import { vaultGate } from "./trash.js";

export function mountHiddenPage(host: HTMLElement): () => void {
  const grid = h("div", { class: "tile-grid" });
  const unbindTiles = bindTileSize(grid);
  const unbindSel = bindSelectionClasses(grid);
  const note = h("p", { style: "margin:0 0 12px;color:var(--text-faint);font-size:12.5px" },
    "Hidden items stay out of the Library, search, People, Collections & Duplicates until you unhide them.");
  const pad = h(
    "div",
    { class: "view-pad" },
    note,
    grid,
  );
  host.append(pad);
  let items: Media[] = [];
  let vaultOk = false;

  function render(): void {
    if (!vaultOk) {
      grid.replaceChildren(
        h("div", { class: "empty-center" }, h("div", { class: "empty-card glass-panel" },
          h("span", { class: "empty-title" }, "Locked"),
          h("span", { class: "empty-sub" }, "Your vault passkey, or device unlock where it is set up, is required to view Hidden."),
        )),
      );
      return;
    }
    if (items.length === 0) {
      grid.replaceChildren(
        h("div", { class: "empty-center", style: "grid-column:1/-1" },
          h("div", { class: "empty-card glass-panel" },
            iconEl("eyeOff"),
            h("span", { class: "empty-title" }, "Nothing hidden"),
            h("span", { class: "empty-sub" }, "Hide items from the viewer or the selection bar & they wait here."),
          )),
      );
      return;
    }
    grid.replaceChildren(
      ...items.map((item) => {
        const tile = tileFor(item, () => items.map((m) => m.id), false);
        const unhideBtn = h("button", { class: "btn", type: "button", style: "position:absolute;left:6px;bottom:6px;padding:3px 10px;font-size:11.5px" }, "Unhide");
        unhideBtn.addEventListener("click", async (event) => {
          event.stopPropagation();
          await api(`/hidden/${item.id}/unhide`, { method: "POST" });
          items = items.filter((m) => m.id !== item.id);
          invalidateMedia();
          void refreshSummary();
          render();
          toast("Back in the Library");
        });
        tile.append(unhideBtn);
        return tile;
      }),
    );
  }

  async function load(): Promise<void> {
    try {
      const data = await api<{ items: Media[] }>("/hidden");
      items = data.items;
      for (const item of items) state.byId.set(item.id, item);
      render();
    } catch (err) {
      if ((err as { status?: number }).status === 401) {
        const ok = await vaultGate();
        if (ok) {
          vaultOk = true;
          return load();
        }
        history.back();
      } else {
        toast(String((err as Error).message), "error");
      }
    }
  }

  render();
  void (async () => {
    const ok = await vaultGate();
    if (!ok) {
      history.back();
      return;
    }
    vaultOk = true;
    await load();
  })();
  return () => {
    clearVaultToken();
    unbindTiles();
    unbindSel();
  };
}
