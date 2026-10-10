import { api, faceThumbUrl } from "../../engine/api.js";
import { countFmt, dayLabel } from "../../engine/format.js";
import { loadAlbums, loadPeople, navigate, on, pageFor, loadMore, refreshSummary, state } from "../../engine/store.js";
import { h } from "../dom.js";
import { iconEl, type IconName } from "../icons.js";
import type { QuerySpec } from "../../engine/store.js";
import { createAlbumFlow } from "./albums.js";
import { loadImage, loadThumb } from "./grid.js";
import { specHash } from "./organize.js";
import { mediaTypeCards } from "./pages.js";
import { placesStrip, tripsStrip } from "./places.js";
import { contentCards, petsStrip } from "./discover.js";

function countCard(label: string, icon: IconName, key: string, hash: string, locked = false): HTMLElement {
  const count = h("span", { class: "card-count" }, "");
  count.dataset.key = key;
  const card = h(
    "button",
    { class: "count-card glass-panel", type: "button" },
    iconEl(icon),
    h("span", { class: "card-label" }, label),
    count,
    h("span", { class: "row-tail" }, iconEl(locked ? "lock" : "chevron")),
  );
  card.addEventListener("click", () => navigate(hash));
  return card;
}

function emptyState(icon: IconName, title: string, sub: string): HTMLElement {
  return h(
    "div",
    { class: "empty-card glass-panel" },
    iconEl(icon),
    h("span", { class: "empty-title" }, title),
    h("span", { class: "empty-sub" }, sub),
  );
}

export function mountCollections(host: HTMLElement): () => void {
  const recentStrip = h("div", { class: "strip" });
  const peopleStrip = h("div", { class: "strip" });
  const albumsStrip = h("div", { class: "strip" });
  const mediaCards = h("div", { class: "cards-grid" });
  const disposeTypes = mediaTypeCards(mediaCards);
  const placesBody = h("div", { class: "strip-reserve" });
  const tripsBody = h("div", { class: "strip-reserve" });
  const disposePlaces = placesStrip(placesBody);
  const disposeTrips = tripsStrip(tripsBody);
  const petsBody = h("div", { class: "strip-reserve" });
  const disposePets = petsStrip(petsBody);
  const contentBody = h("div", { class: "cards-grid" });
  const disposeContent = contentCards(contentBody);
  const utilCards = h("div", { class: "cards-grid" },
    countCard("Favorites", "heart", "favorites", "#/f/favorites"),
    countCard("Recently Deleted", "trash", "trash", "#/trash", true),
    countCard("Hidden", "eyeOff", "hidden", "#/hidden", true),
    countCard("Recently Viewed", "eye", "recently_viewed", "#/f/recently_viewed"),
    countCard("Recently Saved", "save", "total", "#/f/recently_saved"),
    countCard("Recently Edited", "wand", "edited", specHash({ rules: [{ field: "flag", value: "edited" }], sort: "edited", title: "Recently Edited" } as QuerySpec)),
    countCard("Imports", "upload", "imports", "#/imports"),
    countCard("Keywords", "tag", "keywords", "#/keywords"),
    countCard("Duplicates", "dupes", "dup_sets", "#/dedup"),
  );
  const newAlbumBtn = h("button", { class: "btn", type: "button" }, iconEl("plus"), "Create");
  newAlbumBtn.addEventListener("click", createAlbumFlow);

  interface SectionSpec {
    key: string;
    title: string;
    extras: HTMLElement[];
    body: HTMLElement;
  }

  const SECTIONS: SectionSpec[] = [
    { key: "recent", title: "Recent Days", extras: [], body: recentStrip },
    {
      key: "people", title: "People",
      extras: [h("button", { class: "btn", type: "button", onclick: () => navigate("#/people") }, "See All")],
      body: peopleStrip,
    },
    { key: "albums", title: "Albums", extras: [newAlbumBtn], body: albumsStrip },
    {
      key: "pets", title: "Pets",
      extras: [h("button", { class: "btn", type: "button", onclick: () => navigate("#/pets") }, "See All")],
      body: petsBody,
    },
    { key: "media_types", title: "Media Types", extras: [], body: mediaCards },
    {
      key: "content", title: "Content",
      extras: [h("button", { class: "btn", type: "button", onclick: () => navigate("#/subjects") }, "Subjects")],
      body: contentBody,
    },
    { key: "utilities", title: "Utilities", extras: [], body: utilCards },
    { key: "memories", title: "Memories", extras: [], body: h("div", { class: "empty-center" }, emptyState("sparkle", "No Memories Yet", "Automatic Memories are on the roadmap; nothing is generated in this build.")) },
    {
      key: "places", title: "Places",
      extras: [h("button", { class: "btn", type: "button", onclick: () => navigate("#/places") }, iconEl("map"), "Map")],
      body: placesBody,
    },
    {
      key: "trips", title: "Trips",
      extras: [h("button", { class: "btn", type: "button", onclick: () => navigate("#/trips") }, "See All")],
      body: tripsBody,
    },
    { key: "shared", title: "Shared Albums", extras: [], body: h("div", { class: "empty-center" }, emptyState("people", "Sharing Not Built Yet", "DAM is local-first today; shared albums arrive w/ sync support.")) },
  ];

  let layout: { order: string[]; hidden: string[]; collapsed: string[] } = { order: SECTIONS.map((sec) => sec.key), hidden: [], collapsed: [] };
  let editMode = false;
  const editBtn = h("button", { class: "btn", type: "button" }, iconEl("sliders"), "Customize");
  const sectionsWrap = h("div", {});
  const pad = h(
    "div",
    { class: "view-pad" },
    h("div", { class: "section-head" }, h("h2", {}, "Collections"), h("span", { class: "head-spacer" }), editBtn),
    sectionsWrap,
  );
  host.append(pad);

  async function saveLayout(): Promise<void> {
    await api("/prefs/collections", { method: "PUT", body: JSON.stringify({ value: layout }) });
  }

  function buildSections(): void {
    const ordered = [
      ...layout.order.map((key) => SECTIONS.find((sec) => sec.key === key)).filter(Boolean) as SectionSpec[],
      ...SECTIONS.filter((sec) => !layout.order.includes(sec.key)),
    ];
    const nodes: HTMLElement[] = [];
    for (const spec of ordered) {
      const isHidden = layout.hidden.includes(spec.key);
      if (isHidden && !editMode) continue;
      const head = h("div", { class: "section-head" });
      if (editMode) {
        const handle = h("span", { class: "drag-handle", draggable: "true" }, iconEl("move"));
        handle.addEventListener("dragstart", (event) => {
          (event as DragEvent).dataTransfer?.setData("text/dam-section", spec.key);
        });
        head.append(handle);
        head.addEventListener("dragover", (event) => {
          event.preventDefault();
          head.classList.add("drag-over");
        });
        head.addEventListener("dragleave", () => head.classList.remove("drag-over"));
        head.addEventListener("drop", (event) => {
          event.preventDefault();
          head.classList.remove("drag-over");
          const from = (event as DragEvent).dataTransfer?.getData("text/dam-section");
          if (!from || from === spec.key) return;
          const order = layout.order.filter((k) => k !== from);
          order.splice(order.indexOf(spec.key), 0, from);
          layout.order = order;
          void saveLayout();
          buildSections();
        });
      }
      const isCollapsed = layout.collapsed.includes(spec.key);
      const collapseBtn = h("button", { class: `icon-btn collapse-btn${isCollapsed ? " closed" : ""}`, type: "button", "aria-label": isCollapsed ? "Expand section" : "Collapse section" }, iconEl("chevron"));
      collapseBtn.addEventListener("click", () => {
        layout.collapsed = isCollapsed ? layout.collapsed.filter((k) => k !== spec.key) : [...layout.collapsed, spec.key];
        void saveLayout();
        buildSections();
      });
      head.append(collapseBtn, h("h2", { style: isHidden ? "opacity:0.4" : "" }, spec.title), h("span", { class: "head-spacer" }));
      if (editMode) {
        const toggle = h("button", { class: "icon-btn section-hidden-toggle", type: "button", "aria-label": isHidden ? "Show section" : "Hide section" },
          iconEl(isHidden ? "eyeOff" : "eye"));
        toggle.addEventListener("click", () => {
          layout.hidden = isHidden ? layout.hidden.filter((k) => k !== spec.key) : [...layout.hidden, spec.key];
          void saveLayout();
          buildSections();
        });
        head.append(toggle);
      } else {
        head.append(...spec.extras);
      }
      nodes.push(head);
      if (!isHidden && !layout.collapsed.includes(spec.key)) nodes.push(spec.body);
    }
    sectionsWrap.replaceChildren(...nodes);
    pad.classList.toggle("collections-edit", editMode);
  }

  editBtn.addEventListener("click", () => {
    editMode = !editMode;
    editBtn.classList.toggle("primary", editMode);
    editBtn.replaceChildren(iconEl(editMode ? "check" : "sliders"), editMode ? "Done" : "Customize");
    buildSections();
  });

  void api<{ value: { order: string[]; hidden: string[]; collapsed?: string[] } | null }>("/prefs/collections").then((saved) => {
    if (saved.value) layout = { order: saved.value.order ?? layout.order, hidden: saved.value.hidden ?? [], collapsed: (saved.value as { collapsed?: string[] }).collapsed ?? [] };
    buildSections();
  });
  buildSections();

  function renderCounts(): void {
    const summary = state.summary as Record<string, number> | null;
    if (!summary) return;
    pad.querySelectorAll<HTMLElement>(".card-count").forEach((node) => {
      const key = node.dataset.key;
      if (key && key in summary) node.textContent = countFmt(summary[key]);
    });
  }

  function renderRecentDays(): void {
    const items = pageFor("all").items;
    const seen = new Set<string>();
    const cards: HTMLElement[] = [];
    for (const item of items) {
      const label = dayLabel(item.created_ts);
      if (seen.has(label)) continue;
      seen.add(label);
      const img = h("img", { alt: "", loading: "lazy" }) as HTMLImageElement;
      loadThumb(img, item.id, 384);
      const card = h(
        "div",
        { class: "strip-card" },
        h("div", { class: "strip-cover" }, img),
        h("div", { class: "strip-label" }, label),
      );
      card.addEventListener("click", () => navigate("#/library"));
      cards.push(card);
    }
    if (cards.length === 0) {
      recentStrip.replaceChildren(h("div", { class: "empty-center" }, emptyState("image", "Nothing imported yet", "Use Import in the sidebar to bring media into the library.")));
      return;
    }
    recentStrip.replaceChildren(...cards);
  }

  function renderPeople(): void {
    const cards = state.people.map((person) => {
      const img = h("img", { alt: "", loading: "lazy" }) as HTMLImageElement;
      if (person.cover_face_id) {
        loadImage(img, faceThumbUrl(person.cover_face_id));
      }
      const card = h(
        "div",
        { class: "strip-card" },
        h("div", { class: "strip-cover" }, img),
        h("div", { class: "strip-label" }, person.name ?? "Unnamed"),
        h("div", { class: "strip-sub" }, `${countFmt(person.media)} items`),
      );
      card.addEventListener("click", () => navigate(`#/person/${person.id}`));
      return card;
    });
    peopleStrip.replaceChildren(...(cards.length ? cards : [h("div", { class: "empty-center" }, emptyState("people", "No People Yet", "Run a face scan from the People page."))]));
  }

  function renderAlbums(): void {
    const cards = state.albums.map((album) => {
      const cover = h("div", { class: "strip-cover" });
      if (album.cover_media_id) {
        const img = h("img", { alt: "", loading: "lazy" }) as HTMLImageElement;
        loadThumb(img, album.cover_media_id, 384);
        cover.append(img);
      }
      const card = h(
        "div",
        { class: "strip-card" },
        cover,
        h("div", { class: "strip-label" }, album.name),
        h("div", { class: "strip-sub" }, album.is_private ? "Private" : `${countFmt(album.count)} items`),
      );
      card.addEventListener("click", () => navigate(`#/album/${album.id}`));
      return card;
    });
    albumsStrip.replaceChildren(...(cards.length ? cards : [h("div", { class: "empty-center" }, emptyState("albums", "No Albums Available", "Albums appear here once you create them."))]));
  }

  const offs = [
    on("summary", renderCounts),
    on("page", renderRecentDays),
    on("people", renderPeople),
    on("albums", renderAlbums),
  ];
  renderCounts();
  renderRecentDays();
  renderPeople();
  renderAlbums();
  void refreshSummary();
  void loadMore("all");
  void loadPeople();
  void loadAlbums();
  return () => {
    disposeTypes();
    disposePlaces();
    disposeTrips();
    disposePets();
    disposeContent();
    offs.forEach((off) => off());
  };
}
