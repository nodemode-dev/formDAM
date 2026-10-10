import { prefGet, prefSet } from "../../engine/prefstore.js";
import { api, setAlbumToken, thumbUrl } from "../../engine/api.js";
import { countFmt } from "../../engine/format.js";
import { loadAlbums, navigate, on, refreshSummary, state } from "../../engine/store.js";
import type { Album, Media } from "../../engine/types.js";
import { openContextMenu } from "../contextmenu.js";
import { type IconName } from "../icons.js";
import { bindTileSize } from "../zoomctl.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { openModal, textField } from "../modal.js";
import { toast } from "../toast.js";
import { bindSelectionClasses, loadThumb, tileFor } from "./grid.js";

export function unlockAlbumFlow(album: Album): Promise<boolean> {
  return new Promise((resolve) => {
    const modal = openModal(`Unlock "${album.name}"`);
    const { wrap, input } = textField("Passkey", "password", "Enter the album passkey");
    const unlockBtn = h("button", { class: "btn primary", type: "button" }, iconEl("lock"), "Unlock");
    let settled = false;
    const done = (ok: boolean) => {
      if (!settled) {
        settled = true;
        resolve(ok);
      }
    };
    unlockBtn.addEventListener("click", async () => {
      try {
        const res = await api<{ token: string }>(`/albums/${album.id}/unlock`, {
          method: "POST",
          body: JSON.stringify({ passkey: input.value }),
        });
        setAlbumToken(album.id, res.token);
        modal.close();
        done(true);
      } catch (err) {
        toast(String((err as Error).message), "error");
      }
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") unlockBtn.click();
    });
    modal.root.addEventListener("transitionend", () => {
      if (!document.body.contains(modal.root)) done(false);
    });
    modal.body.append(wrap, h("div", { class: "modal-actions" }, unlockBtn));
    input.focus();
  });
}

export function createAlbumFlow(): void {
  const modal = openModal("New Album");
  const { wrap: nameWrap, input: nameInput } = textField("Name", "text", "Album name");
  const privateCheck = h("input", { type: "checkbox" }) as HTMLInputElement;
  const { wrap: keyWrap, input: keyInput } = textField("Passkey", "password", "At least 4 characters");
  keyWrap.classList.add("hidden");
  privateCheck.addEventListener("change", () => keyWrap.classList.toggle("hidden", !privateCheck.checked));
  const createBtn = h("button", { class: "btn primary", type: "button" }, iconEl("plus"), "Create");
  createBtn.addEventListener("click", async () => {
    try {
      const made = await api<Album>("/albums", {
        method: "POST",
        body: JSON.stringify({
          name: nameInput.value,
          is_private: privateCheck.checked,
          passkey: privateCheck.checked && keyInput.value ? keyInput.value : null,
        }),
      });
      modal.close();
      await loadAlbums();
      void refreshSummary();
      navigate(`#/album/${made.id}`);
    } catch (err) {
      toast(String((err as Error).message), "error");
    }
  });
  modal.body.append(
    nameWrap,
    h("label", { class: "field-check" }, privateCheck, "Private album (passkey required to open)"),
    keyWrap,
    h("div", { class: "modal-actions" }, createBtn),
  );
  nameInput.focus();
}

export function mountAlbumsPage(host: HTMLElement): () => void {
  const grid = h("div", { class: "cards-grid" });
  const newBtn = h("button", { class: "btn primary", type: "button" }, iconEl("plus"), "New Album");
  newBtn.addEventListener("click", createAlbumFlow);
  let collapsed = prefGet<boolean>("albumsPage.collapsed", false);
  const collapseBtn = h("button", { class: `icon-btn collapse-btn${collapsed ? " closed" : ""}`, type: "button", "aria-label": "Collapse albums" }, iconEl("chevron"));
  collapseBtn.addEventListener("click", () => {
    collapsed = !collapsed;
    prefSet("albumsPage.collapsed", collapsed);
    collapseBtn.classList.toggle("closed", collapsed);
    grid.classList.toggle("collapsed", collapsed);
  });
  if (collapsed) grid.classList.add("collapsed");
  const pad = h(
    "div",
    { class: "view-pad" },
    h("div", { class: "section-head" }, collapseBtn, h("h2", {}, "Albums"), h("span", { class: "head-spacer" }), newBtn),
    grid,
  );
  host.append(pad);

  function render(): void {
    const cards = state.albums.map((album) => {
      const card = h(
        "button",
        { class: "count-card glass-panel", type: "button" },
        iconEl(album.is_private ? "lock" : "albums"),
        h("span", { class: "card-label" }, album.name),
        h("span", { class: "card-count" }, countFmt(album.count)),
        h("span", { class: "row-tail" }, iconEl("chevron")),
      );
      card.addEventListener("click", () => navigate(`#/album/${album.id}`));
      card.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        openContextMenu(event.clientX, event.clientY, [
          { label: "Open", icon: "folder", action: () => navigate(`#/album/${album.id}`) },
          { label: "Rename...", icon: "type", action: () => {
            const modal = openModal("Rename album");
            const { wrap, input } = textField("Name", "text", album.name);
            input.value = album.name;
            const go = h("button", { class: "btn primary", type: "button" }, "Save");
            go.addEventListener("click", async () => {
              try {
                await api(`/albums/${album.id}`, { method: "PATCH", body: JSON.stringify({ name: input.value.trim() }) }, album.id);
                modal.close();
                void loadAlbums();
              } catch (err) {
                toast(String((err as Error).message), "error");
              }
            });
            modal.body.append(wrap, h("div", { class: "modal-actions" }, go));
            input.focus();
          } },
          "sep",
          { label: "Delete Album...", icon: "trash", danger: true, action: () => {
            const modal = openModal("Delete album?");
            modal.body.append(h("p", { class: "settings-hint" }, `"${album.name}" is removed; its items stay in the Library.`));
            const go = h("button", { class: "btn danger", type: "button" }, "Delete");
            go.addEventListener("click", async () => {
              try {
                await api(`/albums/${album.id}`, { method: "DELETE" }, album.id);
                modal.close();
                void loadAlbums();
              } catch (err) {
                toast(String((err as Error).message), "error");
              }
            });
            modal.body.append(h("div", { class: "modal-actions" }, go));
          } },
        ]);
      });
      return card;
    });
    if (cards.length === 0) {
      grid.replaceChildren(
        h("div", { class: "empty-center" }, h("div", { class: "empty-card glass-panel" },
          iconEl("albums"),
          h("span", { class: "empty-title" }, "No Albums Yet"),
          h("span", { class: "empty-sub" }, "Albums you create appear here. Private albums stay locked behind their passkey."),
        )),
      );
      return;
    }
    grid.replaceChildren(...cards);
  }

  const off = on("albums", render);
  render();
  void loadAlbums();
  return off;
}

export function mountAlbumDetail(host: HTMLElement, albumId: number): () => void {
  const title = h("h2", {}, "Album");
  const sub = h("span", { class: "card-count" }, "");
  const grid = h("div", { class: "tile-grid" });
  const unbindTiles = bindTileSize(grid);
  const unbindSel = bindSelectionClasses(grid);
  let suppressClick = false;
  let sortMode: "manual" | "newest" | "oldest" | "name" | "size" =
    prefGet<"manual">(`albumSort.${albumId}`, "manual");
  const sortBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Sort" }, iconEl("sortLines"));
  sortBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    const rect = sortBtn.getBoundingClientRect();
    const pick = (mode: typeof sortMode) => () => {
      sortMode = mode;
      prefSet(`albumSort.${albumId}`, mode);
      renderItems();
    };
    const mark = (mode: typeof sortMode, label: string, icon: IconName) => ({
      label,
      icon,
      selected: sortMode === mode,
      action: pick(mode),
    });
    openContextMenu(rect.left, rect.bottom + 6, [
      mark("manual", "Manual (drag to arrange)", "sortManual"),
      mark("newest", "Newest first", "sortNewest"),
      mark("oldest", "Oldest first", "sortOldest"),
      mark("name", "Name", "sortName"),
      mark("size", "File size", "sortSize"),
    ]);
  });
  const renameBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Rename" }, iconEl("type"));
  const deleteBtn = h("button", { class: "icon-btn danger", type: "button", "aria-label": "Delete album" }, iconEl("trash"));
  const pad = h(
    "div",
    { class: "view-pad" },
    h("div", { class: "section-head" }, title, sub, h("span", { class: "head-spacer" }), sortBtn, renameBtn, deleteBtn),
    grid,
  );
  host.append(pad);
  let items: Media[] = [];


  function sorted(): Media[] {
    const copy = [...items];
    if (sortMode === "newest") copy.sort((a, b) => b.created_ts - a.created_ts);
    else if (sortMode === "oldest") copy.sort((a, b) => a.created_ts - b.created_ts);
    else if (sortMode === "name") copy.sort((a, b) => a.name.localeCompare(b.name));
    else if (sortMode === "size") copy.sort((a, b) => b.size - a.size);
    return copy;
  }

  function renderItems(): void {
    const view = sorted();
    const nodes = view.map((item) => {
      const tile = tileFor(item, () => view.map((m) => m.id), false);
      if (sortMode === "manual") {
        tile.classList.add("reorderable");
        tile.addEventListener("pointerdown", (event) => {
          if (event.button !== 0) return;
          const startX = event.clientX;
          const startY = event.clientY;
          let lifted = false;
          let target: HTMLElement | null = null;
          let before = false;
          const move = (ev: PointerEvent) => {
            if (!lifted) {
              if (Math.hypot(ev.clientX - startX, ev.clientY - startY) < 7) return;
              lifted = true;
              tile.classList.add("drag-src");
              tile.setPointerCapture(event.pointerId);
            }
            const over = document.elementFromPoint(ev.clientX, ev.clientY)?.closest<HTMLElement>(".tile.reorderable");
            if (target && target !== over) target.classList.remove("drop-before", "drop-after");
            if (!over || over === tile) {
              target = null;
              return;
            }
            target = over;
            const rect2 = over.getBoundingClientRect();
            before = ev.clientX < rect2.left + rect2.width / 2;
            over.classList.toggle("drop-before", before);
            over.classList.toggle("drop-after", !before);
          };
          const up = async () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
            window.removeEventListener("pointercancel", up);
            tile.classList.remove("drag-src");
            const dropTarget = target;
            target?.classList.remove("drop-before", "drop-after");
            if (!lifted) return;
            suppressClick = true;
            setTimeout(() => {
              suppressClick = false;
            }, 150);
            if (!dropTarget) return;
            const targetId = Number(dropTarget.dataset.id);
            if (!targetId || targetId === item.id) return;
            const order = items.map((m) => m.id).filter((mid) => mid !== item.id);
            const at = order.indexOf(targetId) + (before ? 0 : 1);
            order.splice(at, 0, item.id);
            items.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
            renderItems();
            await api(`/albums/${albumId}/order`, { method: "PUT", body: JSON.stringify({ media_ids: order }) }, albumId);
          };
          window.addEventListener("pointermove", move);
          window.addEventListener("pointerup", up);
          window.addEventListener("pointercancel", up);
        });
        tile.addEventListener("click", (event) => {
          if (suppressClick) {
            event.preventDefault();
            event.stopImmediatePropagation();
          }
        }, true);
      }
      return tile;
    });
    grid.replaceChildren(...nodes);
  }

  async function load(): Promise<void> {
    const album = state.albums.find((a) => a.id === albumId);
    try {
      const detail = await api<Album & { items: Media[] }>(`/albums/${albumId}`, undefined, albumId);
      title.textContent = detail.name;
      items = detail.items ?? [];
      sub.textContent = `${countFmt(items.length)} items${detail.is_private ? " · private" : ""}`;
      for (const item of items) state.byId.set(item.id, item);
      renderItems();
      if (items.length === 0) {
        grid.replaceChildren(
          h("div", { class: "empty-center" }, h("div", { class: "empty-card glass-panel" },
            iconEl("image"),
            h("span", { class: "empty-title" }, "Nothing here yet"),
            h("span", { class: "empty-sub" }, "Select items in the Library, then Add to Album."),
          )),
        );
      }
    } catch (err) {
      if ((err as { status?: number }).status === 401 && album) {
        const ok = await unlockAlbumFlow(album);
        if (ok) return load();
        navigate("#/albums");
      } else {
        toast(String((err as Error).message), "error");
      }
    }
  }

  renameBtn.addEventListener("click", () => {
    const modal = openModal("Rename Album");
    const { wrap, input } = textField("Name", "text", title.textContent ?? "");
    input.value = title.textContent ?? "";
    const save = h("button", { class: "btn primary", type: "button" }, "Save");
    save.addEventListener("click", async () => {
      try {
        await api(`/albums/${albumId}`, { method: "PATCH", body: JSON.stringify({ name: input.value }) }, albumId);
        modal.close();
        await loadAlbums();
        void load();
      } catch (err) {
        toast(String((err as Error).message), "error");
      }
    });
    modal.body.append(wrap, h("div", { class: "modal-actions" }, save));
    input.focus();
  });

  deleteBtn.addEventListener("click", async () => {
    try {
      await api(`/albums/${albumId}`, { method: "DELETE" }, albumId);
      await loadAlbums();
      void refreshSummary();
      navigate("#/albums");
      toast("Album deleted; its items stay in the Library");
    } catch (err) {
      toast(String((err as Error).message), "error");
    }
  });

  void load();
  return () => {
    unbindTiles();
    unbindSel();
  };
}

export function albumCoverImg(album: Album): HTMLElement {
  const cover = h("div", { class: "strip-cover" });
  if (album.cover_media_id) {
    const img = h("img", { alt: "", loading: "lazy" }) as HTMLImageElement;
    loadThumb(img, album.cover_media_id, thumbSize());
    cover.append(img);
  }
  return cover;
}

function thumbSize(): number {
  return 384;
}

export function albumThumbUrl(mediaId: number): string {
  return thumbUrl(mediaId, 384);
}
