import { countFmt } from "../../engine/format.js";
import { on, quickRules, refreshSummary, setGrouping, setSort, state } from "../../engine/store.js";
import { openQuickFilters } from "./organize.js";
import { isPinned, togglePin } from "./sidebar.js";
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
  if (filter.startsWith("spec:")) {
    try {
      return (JSON.parse(filter.slice(5)) as { title?: string }).title ?? "Results";
    } catch {
      return "Results";
    }
  }
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
      { label: "Recently added", icon: "save", selected: state.sort === "added", action: () => setSort("added") },
      { label: "First added", icon: "save", selected: state.sort === "added_oldest", action: () => setSort("added_oldest") },
      { label: "Name A to Z", icon: "sortName", selected: state.sort === "name", action: () => setSort("name") },
      { label: "Name Z to A", icon: "sortName", selected: state.sort === "name_desc", action: () => setSort("name_desc") },
      { label: "Largest first", icon: "sortSize", selected: state.sort === "size", action: () => setSort("size") },
      { label: "Smallest first", icon: "sortSize", selected: state.sort === "size_small", action: () => setSort("size_small") },
      { label: "Recently viewed", icon: "eye", selected: state.sort === "viewed", action: () => setSort("viewed") },
      { label: "Highest rated", icon: "star", selected: state.sort === "rating", action: () => setSort("rating") },
      { label: "Recently edited", icon: "wand", selected: state.sort === "edited", action: () => setSort("edited") },
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

  const quickBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Quick filters", title: "Filter by rating, label and more" }, iconEl("star"));
  const paintQuick = () => quickBtn.classList.toggle("active", quickRules().length > 0);
  quickBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    openQuickFilters(quickBtn);
  });
  paintQuick();
  const pinHash = location.hash;
  const pinBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Pin to sidebar", title: "Pin to sidebar" }, iconEl("pin"));
  pinBtn.classList.toggle("active", isPinned(pinHash));
  pinBtn.addEventListener("click", () => {
    const on = togglePin({ label: filterTitle(filter), hash: pinHash, icon: "pin" });
    pinBtn.classList.toggle("active", on);
  });
  const controls: HTMLElement[] = isLibraryRoot
    ? [searchWrap, seg, quickBtn, sortBtn, zoomWrap, menuAnchor]
    : [searchWrap, quickBtn, sortBtn, zoomWrap, pinBtn];

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
  const offs = [on("grouping", renderSeg), on("summary", renderCount), on("media", paintQuick)];
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
