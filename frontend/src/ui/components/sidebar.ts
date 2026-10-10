import { api } from "../../engine/api.js";
import { countFmt } from "../../engine/format.js";
import { navigate, on, state } from "../../engine/store.js";
import { h } from "../dom.js";
import { iconEl, type IconName } from "../icons.js";
import { openSettings } from "./settings.js";

interface RowSpec {
  label: string;
  icon: IconName;
  hash: string;
  locked?: boolean;
  countKey?: keyof NonNullable<typeof state.summary>;
}

const PINNED: RowSpec[] = [
  { label: "Favorites", icon: "heart", hash: "#/f/favorites" },
  { label: "Recently Saved", icon: "save", hash: "#/f/recently_saved" },
  { label: "Videos", icon: "video", hash: "#/f/videos" },
  { label: "Screenshots", icon: "screenshot", hash: "#/f/screenshots" },
  { label: "People", icon: "people", hash: "#/people" },
  { label: "Recently Deleted", icon: "trash", hash: "#/trash", locked: true },
];

const UTILITIES: RowSpec[] = [
  { label: "Recently Deleted", icon: "trash", hash: "#/trash", locked: true },
  { label: "Hidden", icon: "eyeOff", hash: "#/hidden", locked: true },
  { label: "Recently Viewed", icon: "eye", hash: "#/f/recently_viewed" },
  { label: "Screen Recordings", icon: "stage", hash: "#/f/screenrecs" },
  { label: "Duplicates", icon: "dupes", hash: "#/dedup" },
  { label: "Import", icon: "upload", hash: "#/import" },
];

function row(spec: RowSpec): HTMLElement {
  const tail = spec.locked ? h("span", { class: "row-tail" }, iconEl("lock")) : h("span", { class: "row-tail" });
  const node = h(
    "button",
    { class: "side-row", type: "button", onclick: () => navigate(spec.hash) },
    iconEl(spec.icon),
    h("span", { class: "row-label" }, spec.label),
    tail,
  );
  node.dataset.hash = spec.hash;
  return node;
}

export function mountSidebar(host: HTMLElement): void {
  const albumsWrap = h("div", { class: "side-section" });
  const version = h("span", { class: "foot-version" }, "");
  const gearBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Settings" }, iconEl("gear"));
  gearBtn.addEventListener("click", openSettings);
  const foot = h("div", { class: "side-foot" }, version, gearBtn);
  void api<{ version: string }>("/health").then((info) => {
    version.textContent = `v${info.version}`;
  });

  const root = h(
    "nav",
    { class: "sidebar" },
    h("div", { class: "side-brand" }, h("img", { class: "brand-mark", src: "/DAM-icon.png", alt: "DAM" }), h("span", {}, "DAM")),
    row({ label: "Library", icon: "grid", hash: "#/library" }),
    row({ label: "Collections", icon: "shapes", hash: "#/collections" }),
    h("div", { class: "side-section" }, h("p", { class: "side-title" }, "Pinned"), ...PINNED.map(row)),
    albumsWrap,
    h("div", { class: "side-section" }, h("p", { class: "side-title" }, "Utilities"), ...UTILITIES.map(row)),
    foot,
  );

  function renderAlbums(): void {
    const rows: HTMLElement[] = [
      h("p", { class: "side-title" }, "Albums"),
      row({ label: "All Albums", icon: "albums", hash: "#/albums" }),
    ];
    for (const album of state.albums) {
      rows.push(
        row({ label: album.name, icon: album.is_private ? "lock" : "folder", hash: `#/album/${album.id}` }),
      );
    }
    albumsWrap.replaceChildren(...rows);
    highlight();
  }

  function highlight(): void {
    const current = location.hash || "#/library";
    root.querySelectorAll<HTMLElement>(".side-row").forEach((node) => {
      node.classList.toggle("active", node.dataset.hash === current);
    });
  }

  on("albums", renderAlbums);
  on("route", highlight);
  renderAlbums();
  highlight();
  host.append(root);
}

export function summaryCount(key: string): string {
  const summary = state.summary as Record<string, number> | null;
  return summary && key in summary ? countFmt(summary[key]) : "";
}
