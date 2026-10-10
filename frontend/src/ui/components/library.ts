import { countFmt } from "../../engine/format.js";
import { on, refreshSummary, setGrouping, setSort, state } from "../../engine/store.js";
import type { FilterName } from "../../engine/types.js";
import { h } from "../dom.js";
import { iconEl, type IconName } from "../icons.js";
import { openContextMenu } from "../contextmenu.js";
import { zoomControl } from "../zoomctl.js";
import { enableMarquee, enablePinchOpen, mountGrid } from "./grid.js";

const FILTER_LABELS: Record<string, string> = {
  all: "All Items",
  favorites: "Favorites",
  photos: "Photos",
  videos: "Videos",
  screenshots: "Screenshots",
  screenrecs: "Screen Recordings",
  not_in_album: "Not in an Album",
  recently_saved: "Recently Saved",
  recently_viewed: "Recently Viewed",
};

export function filterTitle(filter: FilterName): string {
  return FILTER_LABELS[filter] ?? "Library";
}

export function mountLibrary(host: HTMLElement, filter: FilterName, isLibraryRoot: boolean): () => void {
  const subtitle = h("span", { class: "topbar-sub" }, "");
  const title = h("h1", {}, isLibraryRoot ? "Library" : filterTitle(filter));

  const seg = h("div", { class: "seg" });
  (["years", "months", "all"] as const).forEach((mode) => {
    const label = mode === "all" ? "All Photos" : mode[0].toUpperCase() + mode.slice(1);
    const btn = h("button", { type: "button" }, label);
    btn.dataset.mode = mode;
    btn.addEventListener("click", () => setGrouping(mode));
    seg.append(btn);
  });

  const zoomWrap = zoomControl();
  const sortBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Sort" }, iconEl("sortLines"));
  sortBtn.addEventListener("click", (event) => {
    const rect = sortBtn.getBoundingClientRect();
    event.stopPropagation();
    openContextMenu(rect.left, rect.bottom + 6, [
      { label: "Newest first", icon: "sortNewest", selected: state.sort === "newest", action: () => setSort("newest") },
      { label: "Oldest first", icon: "sortOldest", selected: state.sort === "oldest", action: () => setSort("oldest") },
    ]);
  });

  const filterBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Filter" }, iconEl("sliders"));
  const menu = h("div", { class: "menu pop-surface hidden" });
  const menuAnchor = h("div", { class: "menu-anchor" }, filterBtn, menu);
  const filterKeys: FilterName[] = ["all", "favorites", "photos", "videos", "screenshots", "not_in_album"];
  const FILTER_ICONS: Partial<Record<FilterName, IconName>> = {
    all: "library", favorites: "heart", photos: "image", videos: "video",
    screenshots: "screenshot", not_in_album: "albumOff",
  };
  for (const key of filterKeys) {
    const active = key === state.route.param || (isLibraryRoot && key === "all");
    const item = h(
      "button",
      { class: `menu-item${active ? " selected" : ""}`, type: "button" },
      iconEl(FILTER_ICONS[key] ?? "library"),
      h("span", {}, FILTER_LABELS[key]),
    );
    item.addEventListener("click", () => {
      menu.classList.add("hidden");
      location.hash = key === "all" ? "#/library" : `#/f/${key}`;
    });
    menu.append(item);
  }
  filterBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    menu.classList.toggle("hidden");
  });
  document.addEventListener("click", () => menu.classList.add("hidden"));

  const searchInput = h("input", { type: "search", placeholder: "Search", "aria-label": "Search library", spellcheck: "false", autocomplete: "off", autocorrect: "off", autocapitalize: "off" }) as HTMLInputElement;
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && searchInput.value.trim()) {
      location.hash = `#/search/${encodeURIComponent(searchInput.value.trim())}`;
    }
  });
  const searchWrap = h("span", { class: "search-wrap" }, iconEl("search"), searchInput);

  const controls: HTMLElement[] = isLibraryRoot
    ? [searchWrap, seg, sortBtn, zoomWrap, menuAnchor]
    : [searchWrap, sortBtn, zoomWrap];

  const topbar = h(
    "div",
    { class: "topbar" },
    h("div", { class: "topbar-title" }, title, subtitle),
    h("span", { class: "topbar-spacer" }),
    ...controls,
  );
  const view = h("div", { class: "view" });
  host.append(topbar, view);
  const disposeMarquee = enableMarquee(view);
  const disposePinch = enablePinchOpen(view);

  function renderSeg(): void {
    seg.querySelectorAll("button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === state.grouping);
    });
  }

  function renderCount(): void {
    if (!state.summary) return;
    const map: Partial<Record<FilterName, number>> = {
      all: state.summary.total,
      favorites: state.summary.favorites,
      photos: state.summary.photos,
      videos: state.summary.videos,
      screenshots: state.summary.screenshots,
      screenrecs: state.summary.screenrecs,
      recently_viewed: state.summary.recently_viewed,
      recently_saved: state.summary.total,
      not_in_album: undefined,
    };
    const value = map[filter];
    subtitle.textContent = value !== undefined ? `${countFmt(value)} items` : "";
  }

  const offGrid = mountGrid(view, filter, isLibraryRoot);
  const offs = [on("grouping", renderSeg), on("summary", renderCount)];
  renderSeg();
  renderCount();
  void refreshSummary();
  return () => {
    disposeMarquee();
    disposePinch();
    offGrid();
    offs.forEach((off) => off());
  };
}
