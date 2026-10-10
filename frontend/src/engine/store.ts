import { prefGet, prefSet } from "./prefstore.js";
import { api } from "./api.js";
import type {
  Album, DupSet, FilterName, JobState, LibrarySummary, Media, MediaPage, PeopleStatus, PeriodSummary, Person,
} from "./types.js";

export type Topic =
  | "route" | "page" | "summary" | "albums" | "people" | "peopleStatus"
  | "trash" | "dedup" | "viewer" | "selection" | "zoom" | "grouping" | "job" | "media";

type Listener = () => void;

export interface Route {
  view: string;
  param: string;
}

export interface PageState {
  items: Media[];
  next: Record<string, unknown> | null;
  loading: boolean;
  loaded: boolean;
}

const listeners = new Map<Topic, Set<Listener>>();

export function on(topic: Topic, fn: Listener): () => void {
  if (!listeners.has(topic)) listeners.set(topic, new Set());
  listeners.get(topic)!.add(fn);
  return () => listeners.get(topic)!.delete(fn);
}

function emit(topic: Topic): void {
  listeners.get(topic)?.forEach((fn) => fn());
}

export const state = {
  route: { view: "library", param: "" } as Route,
  pages: new Map<FilterName, PageState>(),
  byId: new Map<number, Media>(),
  summary: null as LibrarySummary | null,
  albums: [] as Album[],
  people: [] as Person[],
  peopleStatus: null as PeopleStatus | null,
  trash: [] as Media[],
  trashRetention: 30,
  dedupSets: [] as DupSet[],
  viewer: null as { ids: number[]; index: number } | null,
  selection: new Set<number>(),
  zoom: prefGet<number>("zoom", 184),
  sort: prefGet<SortOrder>("sort", "newest"),
  grouping: prefGet<"all" | "months" | "years">("grouping", "all"),
  periodCache: new Map<string, PeriodSummary>(),
  quick: prefGet<{ flags: string[]; minRating: number; label: string; keyword: string }>(
    "quick", { flags: [], minRating: 0, label: "", keyword: "" }),
};

export function parseRoute(): Route {
  const hash = location.hash.replace(/^#\/?/, "");
  const [view = "library", param = ""] = hash.split("/");
  return { view: view || "library", param: decodeURIComponent(param) };
}

export function navigate(hash: string): void {
  if (location.hash === hash) return;
  location.hash = hash;
}

export function syncRoute(): void {
  state.route = parseRoute();
  state.selection.clear();
  emit("selection");
  emit("route");
}

export function pageFor(filter: FilterName): PageState {
  if (!state.pages.has(filter)) {
    state.pages.set(filter, { items: [], next: null, loading: false, loaded: false });
  }
  return state.pages.get(filter)!;
}

export async function loadMore(filter: FilterName): Promise<void> {
  const page = pageFor(filter);
  if (page.loading || (page.loaded && page.next === null)) return;
  page.loading = true;
  const params = new URLSearchParams({ spec: JSON.stringify(specFor(filter)), limit: "400" });
  if (page.next) params.set("cursor", JSON.stringify(page.next));
  const data = await api<MediaPage>(`/browse?${params.toString()}`);
  for (const item of data.items) state.byId.set(item.id, item);
  page.items.push(...data.items);
  page.next = data.next;
  page.loading = false;
  page.loaded = true;
  emit("page");
}

export function invalidateMedia(): void {
  state.pages.clear();
  state.periodCache.clear();
  emit("page");
}

export async function refreshSummary(): Promise<void> {
  state.summary = await api<LibrarySummary>("/summary");
  emit("summary");
}

export async function periodSummary(level: "month" | "year"): Promise<PeriodSummary> {
  if (!state.periodCache.has(level)) {
    state.periodCache.set(level, await api<PeriodSummary>(`/media/summary?level=${level}`));
  }
  return state.periodCache.get(level)!;
}

export async function loadAlbums(): Promise<void> {
  state.albums = (await api<{ albums: Album[] }>("/albums")).albums;
  emit("albums");
}

export async function loadPeople(): Promise<void> {
  state.people = (await api<{ people: Person[] }>("/people?min_faces=1")).people;
  emit("people");
}

export async function loadPeopleStatus(): Promise<void> {
  state.peopleStatus = await api<PeopleStatus>("/people/status");
  emit("peopleStatus");
}

export async function loadTrash(): Promise<void> {
  const data = await api<{ items: Media[]; retention_days: number }>("/trash");
  state.trash = data.items;
  state.trashRetention = data.retention_days;
  emit("trash");
}

export async function loadDedupSets(): Promise<void> {
  state.dedupSets = (await api<{ sets: DupSet[] }>("/dedup/sets")).sets;
  emit("dedup");
}

export function openViewer(ids: number[], index: number): void {
  state.viewer = { ids, index };
  emit("viewer");
}

export function closeViewer(): void {
  state.viewer = null;
  emit("viewer");
}

export function stepViewer(delta: number): void {
  if (!state.viewer) return;
  const next = state.viewer.index + delta;
  if (next < 0 || next >= state.viewer.ids.length) return;
  state.viewer.index = next;
  emit("viewer");
}

export function setSelected(id: number, on: boolean): void {
  const has = state.selection.has(id);
  if (on === has) return;
  if (on) state.selection.add(id);
  else state.selection.delete(id);
  emit("selection");
}

export function toggleSelect(id: number): void {
  if (state.selection.has(id)) state.selection.delete(id);
  else state.selection.add(id);
  emit("selection");
}

export function clearSelection(): void {
  if (state.selection.size === 0) return;
  state.selection.clear();
  emit("selection");
}

export type SortOrder =
  | "newest" | "oldest" | "added" | "added_oldest" | "name" | "name_desc" | "size" | "size_small" | "rating" | "edited";

export interface QueryRule {
  field: string;
  op?: string;
  value?: unknown;
  rules?: QueryRule[];
  match?: "all" | "any";
}

export interface QuerySpec {
  rules?: QueryRule[];
  match?: "all" | "any";
  sort?: string;
  text?: string;
  fields?: string[];
  expand_stacks?: boolean;
}

const LEGACY_SPECS: Record<string, QuerySpec> = {
  all: {},
  favorites: { rules: [{ field: "flag", value: "favorite" }] },
  photos: { rules: [{ field: "flag", value: "photo" }] },
  videos: { rules: [{ field: "flag", value: "video" }] },
  screenshots: { rules: [{ field: "flag", value: "screenshot" }] },
  screenrecs: { rules: [{ field: "flag", value: "screen_recording" }] },
  not_in_album: { rules: [{ field: "flag", value: "not_in_album" }] },
  recently_saved: { sort: "added" },
  recently_viewed: { rules: [{ field: "flag", value: "viewed" }], sort: "viewed" },
};

const customSpecs = new Map<string, QuerySpec>();

export function specKey(spec: QuerySpec): FilterName {
  const key = `spec:${JSON.stringify(spec)}` as FilterName;
  customSpecs.set(key, spec);
  return key;
}

export function quickRules(): QueryRule[] {
  const rules: QueryRule[] = state.quick.flags.map((flag) => ({ field: "flag", value: flag }));
  if (state.quick.minRating > 0) rules.push({ field: "rating", op: ">=", value: state.quick.minRating });
  if (state.quick.label) rules.push({ field: "label", value: state.quick.label });
  if (state.quick.keyword) rules.push({ field: "keyword", value: state.quick.keyword });
  return rules;
}

export function specFor(filter: FilterName): QuerySpec {
  const custom = customSpecs.get(filter);
  if (custom) return { sort: state.sort, ...custom };
  const base = LEGACY_SPECS[filter] ?? {};
  const rules = [...(base.rules ?? []), ...quickRules()];
  const sort = base.sort && state.sort === "newest" ? base.sort : state.sort;
  return { ...base, rules, sort };
}

export function setQuickFilter(patch: Partial<typeof state.quick>): void {
  Object.assign(state.quick, patch);
  prefSet("quick", state.quick);
  invalidateMedia();
  emit("media");
}

export function hydrateStatePrefs(): void {
  state.zoom = prefGet<number>("zoom", 184);
  state.sort = prefGet<SortOrder>("sort", "newest");
  state.grouping = prefGet<"all" | "months" | "years">("grouping", "all");
}

export function setSort(order: SortOrder): void {
  if (state.sort === order) return;
  state.sort = order;
  prefSet("sort", order);
  invalidateMedia();
  void refreshSummary();
  emit("media");
}

export function setZoom(px: number): void {
  state.zoom = Math.min(512, Math.max(96, px));
  prefSet("zoom", state.zoom);
  emit("zoom");
}

export function setGrouping(mode: "all" | "months" | "years"): void {
  state.grouping = mode;
  prefSet("grouping", mode);
  emit("grouping");
}

export async function setFavorite(id: number, onFlag: boolean): Promise<void> {
  await api(`/media/${id}/favorite`, { method: "POST", body: JSON.stringify({ on: onFlag }) });
  const item = state.byId.get(id);
  if (item) item.favorite = onFlag;
  const favPage = state.pages.get("favorites");
  if (favPage) {
    state.pages.delete("favorites");
  }
  emit("page");
  if (state.viewer) emit("viewer");
}

export async function markViewed(id: number): Promise<void> {
  await api(`/media/${id}/viewed`, { method: "POST" });
  state.pages.delete("recently_viewed");
}

export function dropFromCaches(id: number): void {
  for (const page of state.pages.values()) {
    const at = page.items.findIndex((m) => m.id === id);
    if (at >= 0) page.items.splice(at, 1);
  }
  state.byId.delete(id);
  emit("page");
}

export async function trashMedia(id: number): Promise<void> {
  await api(`/media/${id}/trash`, { method: "POST" });
  dropFromCaches(id);
  void refreshSummary();
}

export function pollJob(jobId: string, done: (job: JobState) => void): void {
  const tick = async () => {
    const job = await api<JobState>(`/jobs/${jobId}`);
    emit("job");
    if (job.phase === "running") {
      setTimeout(tick, 500);
    } else {
      done(job);
    }
  };
  void tick();
}
