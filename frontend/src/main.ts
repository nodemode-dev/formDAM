import { hydrateStatePrefs, loadAlbums, on, refreshSummary, specKey, state, syncRoute } from "./engine/store.js";
import { registerOrganize } from "./ui/components/organize.js";
import { mountImportsPage, mountKeywordsPage } from "./ui/components/pages.js";
import { mountPlacesPage, mountTripsPage, registerPlaces } from "./ui/components/places.js";
import { initPrefs, prefGet } from "./engine/prefstore.js";
import { applyTheme, loadTheme } from "./engine/theme.js";
import { mountBackground } from "./theme/background.js";
import { openSettings, registerBackground } from "./ui/components/settings.js";
import { mountHiddenPage } from "./ui/components/hidden.js";
import { mountSearchPage } from "./ui/components/search.js";
import type { FilterName } from "./engine/types.js";
import { h } from "./ui/dom.js";
import { iconEl } from "./ui/icons.js";
import { mountAlbumDetail, mountAlbumsPage } from "./ui/components/albums.js";
import { mountCollections } from "./ui/components/collections.js";
import { mountDedupPage } from "./ui/components/dedup.js";
import { mountGrid, setPreloadHud } from "./ui/components/grid.js";
import { mountImportPage } from "./ui/components/importer.js";
import { mountLibrary } from "./ui/components/library.js";
import { mountPeoplePage, mountPersonPage } from "./ui/components/people.js";
import { mountSelectBar } from "./ui/components/selectbar.js";
import { mountSidebar } from "./ui/components/sidebar.js";
import { mountTrashPage } from "./ui/components/trash.js";
import { mountViewer } from "./ui/components/viewer.js";

await initPrefs();
hydrateStatePrefs();
{
  const boot = loadTheme();
  // Restore the saved desktop blur & re-assert the transparent webview backdrop.
  const win = { blur: boot.winBlur, clear: true };
  // Hidden-until-painted reveal: the shell keeps the window invisible until the
  // first frame is actually painted (double rAF), so launch shows a finished
  // app & never a backdrop flash.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      void fetch("/api/system/window", { method: "POST", headers: { "content-type": "application/json", "x-dam-local": "1" }, body: JSON.stringify({ ready: true }) }).catch(() => undefined);
    });
  });
  void fetch("/api/system/window", { method: "POST", headers: { "content-type": "application/json", "x-dam-local": "1" }, body: JSON.stringify(win) }).catch(() => undefined);
}
setPreloadHud(prefGet<boolean>("preloadHud", false));
const themePrefs = loadTheme();
applyTheme(themePrefs);

let disposeBackground: (() => void) | null = null;
let remountTimer: number | undefined;

function bgHost(): HTMLElement {
  const app = document.getElementById("app") as HTMLElement;
  let holder = document.getElementById("bg-holder");
  if (!holder) {
    holder = h("div", { id: "bg-holder" });
    app.insertBefore(holder, app.firstChild);
  }
  return holder as HTMLElement;
}

function bgConfig(bg: { radius: number; glow: number; bloom: number }): Record<string, unknown> {
  const glow = Math.min(200, Math.max(0, bg.glow));
  const bloom = Math.min(200, Math.max(0, bg.bloom));
  return {
    pattern: "hexes",
    fillCells: false,
    cell: 46,
    corner: 5,
    lineWidth: 1.6,
    radius: bg.radius,
    strokeAlpha: Math.min(1, glow / 100),
    glowWidth: 1 + (Math.max(0, glow - 100) / 100) * 1.4,
    washAlpha: (bloom / 100) * 0.13,
  };
}

const backgroundControl = {
  enable(): void {
    if (!disposeBackground) {
      disposeBackground = mountBackground(bgHost(), bgConfig(loadTheme().bg)) as () => void;
    }
  },
  disable(): void {
    disposeBackground?.();
    disposeBackground = null;
  },
  update(bg: { radius: number; glow: number; bloom: number }): void {
    window.clearTimeout(remountTimer);
    remountTimer = window.setTimeout(() => {
      if (!disposeBackground) return;
      disposeBackground();
      disposeBackground = mountBackground(bgHost(), bgConfig(bg)) as () => void;
    }, 140);
  },
};
registerBackground(backgroundControl);
if (themePrefs.background) backgroundControl.enable();

window.addEventListener("dam-menu", (event) => {
  if ((event as CustomEvent).detail === "settings") openSettings();
});

window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

document.addEventListener("contextmenu", (event) => {
  const target = event.target as HTMLElement;
  if (target.closest("input, textarea, [contenteditable=\"true\"]")) return;
  event.preventDefault();
});

const app = document.getElementById("app")!;
const content = h("main", { class: "content" });
mountSidebar(app);
app.append(content);
mountViewer(document.body);
registerOrganize();
registerPlaces();
mountSelectBar(document.body);

let teardown: (() => void) | null = null;

function plainShell(titleText: string): HTMLElement {
  const view = h("div", { class: "view" });
  const backBtn = h("button", { class: "icon-btn back-btn", type: "button", "aria-label": "Back" }, iconEl("back"));
  backBtn.addEventListener("click", () => {
    if (history.length > 1) history.back();
    else location.hash = "#/library";
  });
  content.append(
    h("div", { class: "topbar" }, backBtn, h("div", { class: "topbar-title" }, h("h1", {}, titleText)), h("span", { class: "topbar-spacer" })),
    view,
  );
  return view;
}

const scrollMemory = new Map<string, number>();
let lastRouteKey = "";

function saveScroll(): void {
  const scroller = content.querySelector<HTMLElement>(".view");
  if (lastRouteKey && scroller) scrollMemory.set(lastRouteKey, scroller.scrollTop);
}

function restoreScroll(key: string): void {
  lastRouteKey = key;
  const top = scrollMemory.get(key) ?? 0;
  requestAnimationFrame(() => {
    const scroller = content.querySelector<HTMLElement>(".view");
    if (scroller) scroller.scrollTop = top;
    requestAnimationFrame(() => {
      const again = content.querySelector<HTMLElement>(".view");
      if (again && Math.abs(again.scrollTop - top) > 2) again.scrollTop = top;
    });
  });
}

function render(): void {
  saveScroll();
  if (teardown) teardown();
  teardown = null;
  content.replaceChildren();
  const { view, param } = state.route;

  document.documentElement.classList.toggle("route-collections", view === "collections");
  if (view === "library" || view === "") {
    teardown = mountLibrary(content, "all", true);
  } else if (view === "f") {
    const filter = (param || "all") as FilterName;
    teardown = mountLibrary(content, filter, false);
  } else if (view === "collections") {
    teardown = mountCollections(plainShell("Collections"));
  } else if (view === "albums") {
    teardown = mountAlbumsPage(plainShell("Albums"), param ? Number(param) : null);
  } else if (view === "album") {
    teardown = mountAlbumDetail(plainShell("Album"), Number(param));
  } else if (view === "people") {
    teardown = mountPeoplePage(plainShell("People"));
  } else if (view === "person") {
    teardown = mountPersonPage(plainShell("People"), Number(param));
  } else if (view === "trash") {
    teardown = mountTrashPage(plainShell("Recently Deleted"));
  } else if (view === "hidden") {
    teardown = mountHiddenPage(plainShell("Hidden"));
  } else if (view === "search") {
    teardown = mountSearchPage(plainShell("Search"), param);
  } else if (view === "dedup") {
    teardown = mountDedupPage(plainShell("Duplicates"));
  } else if (view === "import") {
    teardown = mountImportPage(plainShell("Import"));
  } else if (view === "q") {
    let key: FilterName = "all";
    try {
      key = specKey(JSON.parse(param));
    } catch {
      key = "all";
    }
    teardown = mountLibrary(content, key, false);
  } else if (view === "imports") {
    teardown = mountImportsPage(plainShell("Imports"));
  } else if (view === "keywords") {
    teardown = mountKeywordsPage(plainShell("Keywords"));
  } else if (view === "places") {
    teardown = mountPlacesPage(plainShell("Places"));
  } else if (view === "trips") {
    teardown = mountTripsPage(plainShell("Trips"));
  } else {
    const shell = plainShell("Library");
    teardown = mountGrid(shell, "all", true);
  }
  restoreScroll(location.hash || "#/library");
}

on("route", render);
window.addEventListener("hashchange", syncRoute);
syncRoute();
void refreshSummary();
void loadAlbums();
