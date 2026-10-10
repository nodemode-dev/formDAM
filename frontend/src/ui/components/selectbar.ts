import { api } from "../../engine/api.js";
import { countFmt } from "../../engine/format.js";
import { clearSelection, dropFromCaches, loadAlbums, on, refreshSummary, state } from "../../engine/store.js";
import { h } from "../dom.js";
import { iconEl, type IconName } from "../icons.js";
import { openModal } from "../modal.js";
import { toast } from "../toast.js";
import { unlockAlbumFlow } from "./albums.js";

export interface ContextAction {
  label: string;
  icon: IconName;
  handler: (ids: number[]) => void;
}

let contextActions: ContextAction[] = [];
let renderContext: () => void = () => undefined;

export function setSelectbarContext(actions: ContextAction[]): () => void {
  contextActions = actions;
  renderContext();
  return () => {
    contextActions = [];
    renderContext();
  };
}

export function mountSelectBar(host: HTMLElement): void {
  const count = h("span", { class: "sel-count" }, "");
  const contextSlot = h("span", { class: "sel-context" });
  renderContext = () => {
    contextSlot.replaceChildren(...contextActions.map((action) => {
      const btn = h("button", { class: "btn", type: "button" }, iconEl(action.icon), action.label);
      btn.addEventListener("click", () => action.handler([...state.selection]));
      return btn;
    }));
  };
  renderContext();
  const addBtn = h("button", { class: "btn", type: "button" }, iconEl("albums"), "Add to Album");
  const hideBtn = h("button", { class: "btn", type: "button" }, iconEl("eyeOff"), "Hide");
  const trashBtn = h("button", { class: "btn danger", type: "button" }, iconEl("trash"), "Delete");
  const clearBtn = h("button", { class: "btn", type: "button" }, "Clear");
  const bar = h("div", { class: "sel-bar pop-surface hidden" }, count, contextSlot, addBtn, hideBtn, trashBtn, clearBtn);
  host.append(bar);

  clearBtn.addEventListener("click", clearSelection);

  hideBtn.addEventListener("click", async () => {
    const ids = [...state.selection];
    for (const id of ids) {
      await api(`/media/${id}/hide`, { method: "POST" });
      dropFromCaches(id);
    }
    clearSelection();
    void refreshSummary();
    toast(`Hid ${countFmt(ids.length)} items`);
  });

  trashBtn.addEventListener("click", async () => {
    const ids = [...state.selection];
    for (const id of ids) {
      await api(`/media/${id}/trash`, { method: "POST" });
      dropFromCaches(id);
    }
    clearSelection();
    void refreshSummary();
    toast(`Moved ${countFmt(ids.length)} to Recently Deleted`);
  });

  addBtn.addEventListener("click", () => {
    addToAlbumFlow([...state.selection], () => clearSelection());
  });

  on("selection", () => {
    const n = state.selection.size;
    bar.classList.toggle("hidden", n === 0);
    count.textContent = n ? `${countFmt(n)} selected` : "";
  });
}

export function addToAlbumFlow(ids: number[], after?: () => void): void {
    const modal = openModal("Add to Album");
    const list = h("div", { class: "list-rows" });
    for (const album of state.albums) {
      const row = h(
        "button",
        { class: "list-row glass-panel", type: "button" },
        iconEl(album.is_private ? "lock" : "folder"),
        h("div", { class: "list-main" }, h("div", { class: "list-title" }, album.name)),
      );
      row.addEventListener("click", async () => {
        const send = async () =>
          api(`/albums/${album.id}/items`, { method: "POST", body: JSON.stringify({ media_ids: ids }) }, album.id);
        try {
          await send();
        } catch (err) {
          if ((err as { status?: number }).status === 401) {
            const ok = await unlockAlbumFlow(album);
            if (!ok) return;
            await send();
          } else {
            toast(String((err as Error).message), "error");
            return;
          }
        }
        modal.close();
        after?.();
        void loadAlbums();
        void refreshSummary();
        toast(`Added ${countFmt(ids.length)} to ${album.name}`);
      });
      list.append(row);
    }
    if (state.albums.length === 0) {
      list.append(h("div", { class: "empty-card glass-panel" },
        h("span", { class: "empty-title" }, "No albums yet"),
        h("span", { class: "empty-sub" }, "Create one from the Albums page first."),
      ));
    }
  modal.body.append(list);
}
