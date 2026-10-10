import { api, fileUrl, stillUrl, thumbUrl } from "../../engine/api.js";
import { countFmt, dayLabel } from "../../engine/format.js";
import { emitTopic, invalidateMedia, navigate, on, pollJob, saveMeta, specKey, state, type QuerySpec } from "../../engine/store.js";
import type { Media } from "../../engine/types.js";
import type { CtxEntry } from "../contextmenu.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { promptText } from "../prompt.js";
import { toast } from "../toast.js";
import { loadThumb, mountGrid, tileHooks } from "./grid.js";
import { specHash } from "./organize.js";
import { selectbarExtras } from "./selectbar.js";
import { viewerHooks } from "./viewer.js";

interface Memory { id: number; kind: string; title: string; subtitle: string | null; key_media_id: number | null; count: number; favorite: number; start_ts: number | null }
interface MemoryDetail extends Memory { ids: number[]; music: { theme: string; path?: string } }
interface Group { key: string; name: string; count: number; cover: number | null; people: number[] }

const THEMES: Array<[string, string]> = [["gentle", "Gentle"], ["uplifting", "Uplifting"], ["dreamy", "Dreamy"], ["none", "No Music"]];

function emptyCard(title: string, sub: string): HTMLElement {
  return h("div", { class: "empty-center hidden" }, h("div", { class: "empty-card glass-panel" }, iconEl("memory"), h("span", { class: "empty-title" }, title), h("span", { class: "empty-sub" }, sub)));
}

function memoryCard(m: Memory): HTMLElement {
  const img = h("img", { alt: "", draggable: false }) as HTMLImageElement;
  if (m.key_media_id) loadThumb(img, m.key_media_id, 768);
  const title = h("div", { class: "memory-title" }, m.title);
  const sub = h("div", { class: "memory-sub" }, m.subtitle || (m.start_ts ? dayLabel(m.start_ts) : ""));
  const play = h("button", { class: "icon-btn memory-play", type: "button", "aria-label": "Play memory" }, iconEl("play"));
  play.addEventListener("click", (event) => {
    event.stopPropagation();
    void playMemory(m.id);
  });
  const card = h("div", { class: "memory-card" }, h("div", { class: "memory-cover" }, img, h("div", { class: "memory-shade" }), h("div", { class: "memory-text" }, title, sub), play));
  card.addEventListener("click", () => navigate(`#/memory/${m.id}`));
  return card;
}

export function memoriesStrip(container: HTMLElement): () => void {
  const strip = h("div", { class: "strip memory-strip" });
  const empty = emptyCard("No Memories Yet", "Memories are built from trips, people, pets, places and this week in past years.");
  container.append(strip, empty);
  let alive = true;
  const refresh = () => void api<{ memories: Memory[] }>("/memories").then((res) => {
    if (!alive) return;
    empty.classList.toggle("hidden", res.memories.length > 0);
    patchList(strip, res.memories.slice(0, 20), (m) => String(m.id), memoryCard,
      (node, m) => setText(node.querySelector(".memory-title") as HTMLElement, m.title));
  });
  refresh();
  const off = on("summary", refresh);
  return () => {
    alive = false;
    off();
  };
}

export function mountMemoriesPage(host: HTMLElement): () => void {
  const grid = h("div", { class: "memory-grid" });
  const empty = emptyCard("No Memories Yet", "Create memories from your library, or select photos and choose Create Memory.");
  const gen = h("button", { class: "btn primary", type: "button" }, iconEl("sparkle"), "Create Memories") as HTMLButtonElement;
  const describe = h("button", { class: "btn", type: "button" }, iconEl("search"), "Describe a Memory...");
  describe.addEventListener("click", async () => {
    const text = await promptText("Describe a Memory", "", "For example: dogs at the beach, Tokyo in May 2025, birthday cake", "Create");
    if (!text) return;
    try {
      const res = await api<{ id: number }>("/memories/prompt", { method: "POST", body: JSON.stringify({ text }) });
      navigate(`#/memory/${res.id}`);
    } catch (err) {
      toast(String((err as Error).message), "error");
    }
  });
  host.append(h("div", { class: "view-pad" }, h("div", { class: "section-head" }, h("h2", {}, "Memories"), h("span", { class: "head-spacer" }), describe, gen), grid, empty));
  let alive = true;
  const load = async () => {
    const res = await api<{ memories: Memory[] }>("/memories");
    if (!alive) return;
    empty.classList.toggle("hidden", res.memories.length > 0);
    patchList(grid, res.memories, (m) => String(m.id), memoryCard, (node, m) => setText(node.querySelector(".memory-title") as HTMLElement, m.title));
  };
  gen.addEventListener("click", async () => {
    gen.disabled = true;
    const job = await api<{ job_id: string }>("/memories/generate", { method: "POST" });
    pollJob(job.job_id, () => { gen.disabled = false; void load(); });
  });
  void load();
  return () => {
    alive = false;
  };
}

export function mountMemoryPage(host: HTMLElement, id: number): () => void {
  const title = h("h2", { class: "memory-page-title" }, "");
  const sub = h("span", { class: "topbar-sub" }, "");
  const play = h("button", { class: "btn primary", type: "button" }, iconEl("play"), "Play");
  const theme = h("select", { class: "field-input compact" }) as HTMLSelectElement;
  for (const [k, label] of THEMES) theme.append(h("option", { value: k }, label));
  const fileOpt = h("option", { value: "file" }, "Audio File...");
  theme.append(fileOpt);
  const fav = h("button", { class: "icon-btn", type: "button", "aria-label": "Favorite memory" }, iconEl("heart"));
  const rename = h("button", { class: "btn", type: "button" }, "Rename");
  const del = h("button", { class: "btn", type: "button" }, "Delete Memory");
  const gridHost = h("div", {});
  host.append(h("div", { class: "view-pad" }, h("div", { class: "section-head" }, title, sub, h("span", { class: "head-spacer" }), theme, fav, rename, del, play)), gridHost);
  let detail: MemoryDetail | null = null;
  let disposeGrid: (() => void) | null = null;
  const load = async () => {
    detail = await api<MemoryDetail>(`/memories/${id}`);
    setText(title, detail.title);
    setText(sub, `${detail.subtitle ? `${detail.subtitle} · ` : ""}${countFmt(detail.ids.length)} items`);
    theme.value = detail.music.path ? "file" : detail.music.theme;
    fav.replaceChildren(iconEl(detail.favorite ? "heartFill" : "heart"));
    if (!disposeGrid) disposeGrid = mountGrid(gridHost, specKey({ rules: [{ field: "memory", value: id }], sort: "oldest", expand_stacks: true } as QuerySpec), false);
  };
  play.addEventListener("click", () => void playMemory(id));
  theme.addEventListener("change", async () => {
    if (theme.value === "file") {
      const path = await promptText("Music for this memory", "", "Full path of an audio file on this computer (mp3, m4a, wav, aiff, flac)", "Use");
      if (!path) { theme.value = detail?.music.theme ?? "gentle"; return; }
      await api(`/memories/${id}`, { method: "PATCH", body: JSON.stringify({ music_path: path }) }).catch((err) => toast(String((err as Error).message), "error"));
    } else {
      await api(`/memories/${id}`, { method: "PATCH", body: JSON.stringify({ theme: theme.value }) });
    }
    void load();
  });
  fav.addEventListener("click", async () => {
    if (!detail) return;
    await api(`/memories/${id}`, { method: "PATCH", body: JSON.stringify({ favorite: !detail.favorite }) });
    void load();
  });
  rename.addEventListener("click", async () => {
    const next = await promptText("Rename Memory", detail?.title ?? "", "", "Save");
    if (!next) return;
    await api(`/memories/${id}`, { method: "PATCH", body: JSON.stringify({ title: next }) });
    void load();
  });
  del.addEventListener("click", async () => {
    await api(`/memories/${id}`, { method: "DELETE" });
    toast("Memory deleted");
    navigate("#/memories");
  });
  void load();
  return () => disposeGrid?.();
}

export function groupsStrip(container: HTMLElement): () => void {
  const strip = h("div", { class: "strip" });
  const empty = h("div", { class: "empty-center hidden" }, h("div", { class: "empty-card glass-panel" }, iconEl("people"),
    h("span", { class: "empty-title" }, "No Groups Yet"), h("span", { class: "empty-sub" }, "People who often appear together form groups after a face scan.")));
  container.append(strip, empty);
  let alive = true;
  const refresh = () => void api<{ groups: Group[] }>("/people/groups").then((res) => {
    if (!alive) return;
    empty.classList.toggle("hidden", res.groups.length > 0);
    patchList(strip, res.groups.slice(0, 20), (g) => g.key, (g) => {
      const img = h("img", { alt: "", draggable: false }) as HTMLImageElement;
      if (g.cover) loadThumb(img, g.cover, 384);
      const label = h("div", { class: "strip-label" }, g.name);
      const rename = h("button", { class: "link-btn", type: "button" }, "Name");
      rename.addEventListener("click", async (event) => {
        event.stopPropagation();
        const name = await promptText("Name this group", g.name, "", "Save");
        if (name === null) return;
        await api(`/people/groups/${g.key}`, { method: "PATCH", body: JSON.stringify({ name }) });
        setText(label, name || g.name);
      });
      const card = h("div", { class: "strip-card" }, h("div", { class: "strip-cover" }, img), label, h("div", { class: "strip-sub" }, `${countFmt(g.count)} items `, rename));
      card.addEventListener("click", () => navigate(specHash({ rules: [{ field: "group", value: g.key }], title: g.name, expand_stacks: true } as QuerySpec)));
      return card;
    }, (node, g) => setText(node.querySelector(".strip-label") as HTMLElement, g.name));
  });
  refresh();
  const off = on("people", refresh);
  return () => {
    alive = false;
    off();
  };
}

class Music {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private timer = 0;
  private audio: HTMLAudioElement | null = null;

  start(theme: string, fileSrc?: string): void {
    this.stop();
    if (theme === "none") return;
    if (fileSrc) {
      this.audio = new Audio(fileSrc);
      this.audio.loop = true;
      this.audio.volume = 0.7;
      void this.audio.play().catch(() => undefined);
      return;
    }
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    this.ctx = ctx;
    const master = ctx.createGain();
    master.gain.value = 0;
    master.gain.linearRampToValueAtTime(0.22, ctx.currentTime + 2);
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = theme === "uplifting" ? 2600 : 1400;
    const delay = ctx.createDelay(1.5);
    delay.delayTime.value = theme === "dreamy" ? 0.55 : 0.38;
    const feedback = ctx.createGain();
    feedback.gain.value = theme === "dreamy" ? 0.45 : 0.25;
    delay.connect(feedback).connect(delay);
    master.connect(filter);
    filter.connect(ctx.destination);
    filter.connect(delay);
    delay.connect(ctx.destination);
    this.master = master;
    const progressions: Record<string, number[][]> = {
      gentle: [[57, 60, 64, 69], [53, 57, 60, 65], [48, 55, 60, 64], [55, 59, 62, 67]],
      uplifting: [[60, 64, 67, 72], [55, 59, 62, 67], [57, 60, 64, 69], [53, 57, 60, 65]],
      dreamy: [[50, 57, 62, 66], [55, 59, 62, 69], [52, 59, 64, 67], [48, 55, 62, 64]],
    };
    const chords = progressions[theme] ?? progressions.gentle;
    const beat = theme === "uplifting" ? 0.42 : theme === "dreamy" ? 0.9 : 0.7;
    let step = 0;
    const hz = (n: number) => 440 * 2 ** ((n - 69) / 12);
    const note = (freq: number, at: number, len: number, gain: number, type: OscillatorType) => {
      const osc = ctx.createOscillator();
      const env = ctx.createGain();
      osc.type = type;
      osc.frequency.value = freq;
      env.gain.setValueAtTime(0, at);
      env.gain.linearRampToValueAtTime(gain, at + Math.min(0.4, len / 3));
      env.gain.exponentialRampToValueAtTime(0.0001, at + len);
      osc.connect(env).connect(master);
      osc.start(at);
      osc.stop(at + len + 0.05);
    };
    const tick = () => {
      if (!this.ctx) return;
      const now = ctx.currentTime + 0.05;
      const chord = chords[Math.floor(step / 8) % chords.length];
      if (step % 8 === 0) for (const n of chord) note(hz(n - 12), now, beat * 8, 0.09, "sine");
      const arp = chord[(step * (theme === "dreamy" ? 1 : 3)) % chord.length] + (step % 16 >= 8 && theme === "uplifting" ? 12 : 0);
      note(hz(arp), now, beat * 1.6, theme === "dreamy" ? 0.05 : 0.07, "triangle");
      step++;
      this.timer = window.setTimeout(tick, beat * 1000);
    };
    tick();
  }

  stop(): void {
    window.clearTimeout(this.timer);
    if (this.audio) {
      this.audio.pause();
      this.audio = null;
    }
    if (this.ctx && this.master) {
      const ctx = this.ctx;
      this.master.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.6);
      setTimeout(() => void ctx.close(), 700);
    }
    this.ctx = null;
    this.master = null;
  }
}

async function playMemory(id: number): Promise<void> {
  const detail = await api<MemoryDetail>(`/memories/${id}`);
  openSlideshow(detail.ids, { title: detail.title, subtitle: detail.subtitle ?? "", theme: detail.music.theme, musicSrc: detail.music.path ? `/api/memories/${id}/music` : undefined });
}

export function openSlideshow(ids: number[], opts: { title?: string; subtitle?: string; theme?: string; musicSrc?: string; start?: number } = {}): void {
  if (!ids.length || document.querySelector(".slideshow")) return;
  let index = opts.start ?? 0;
  let playing = true;
  let timer = 0;
  let interval = 4000;
  const music = new Music();
  const a = h("div", { class: "ss-layer" });
  const b = h("div", { class: "ss-layer" });
  let front = a;
  const caption = h("div", { class: "ss-caption" }, h("div", { class: "ss-title" }, opts.title ?? ""), h("div", { class: "ss-sub" }, opts.subtitle ?? ""));
  const playBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Pause" }, iconEl("pause"));
  const prev = h("button", { class: "icon-btn", type: "button", "aria-label": "Previous" }, iconEl("arrowLeft"));
  const next = h("button", { class: "icon-btn ss-next", type: "button", "aria-label": "Next" }, iconEl("arrowLeft"));
  const close = h("button", { class: "icon-btn", type: "button", "aria-label": "Close slideshow" }, iconEl("close"));
  const theme = h("select", { class: "field-input compact" }) as HTMLSelectElement;
  for (const [k, label] of THEMES) theme.append(h("option", { value: k }, label));
  if (opts.musicSrc) theme.append(h("option", { value: "file" }, "Memory Music"));
  theme.value = opts.musicSrc ? "file" : opts.theme ?? "gentle";
  const speed = h("select", { class: "field-input compact" }) as HTMLSelectElement;
  for (const [ms, label] of [["2500", "Fast"], ["4000", "Normal"], ["6500", "Slow"]]) speed.append(h("option", { value: ms }, label));
  speed.value = "4000";
  const pos = h("span", { class: "ss-pos" }, "");
  const bar = h("div", { class: "ss-bar" }, close, prev, playBtn, next, pos, h("span", { class: "head-spacer" }), theme, speed);
  const root = h("div", { class: "slideshow" }, a, b, caption, bar);
  document.body.append(root);
  requestAnimationFrame(() => root.classList.add("open"));
  const setPlayIcon = () => playBtn.replaceChildren(iconEl(playing ? "pause" : "play"));
  const startMusic = () => music.start(theme.value === "file" ? "file" : theme.value, theme.value === "file" ? opts.musicSrc : undefined);

  function show(i: number): void {
    index = (i + ids.length) % ids.length;
    const id = ids[index];
    const item = state.byId.get(id);
    const back = front === a ? b : a;
    const isVideo = item?.kind === "video";
    const media = isVideo
      ? h("video", { src: fileUrl(id), muted: true, autoplay: true, playsinline: true, class: "ss-media" }) as HTMLVideoElement
      : h("img", { class: "ss-media kenburns", alt: "", draggable: false }) as HTMLImageElement;
    const reveal = () => {
      back.replaceChildren(media);
      back.classList.add("on");
      front.classList.remove("on");
      front = back;
      setText(pos, `${index + 1} / ${ids.length}`);
      caption.classList.toggle("hidden", index !== 0);
    };
    if (media instanceof HTMLImageElement) {
      media.style.setProperty("--kb-x", `${(Math.random() * 6 - 3).toFixed(1)}%`);
      media.style.setProperty("--kb-y", `${(Math.random() * 6 - 3).toFixed(1)}%`);
      media.src = item ? stillUrl(item, 2048) : thumbUrl(id, 768);
      void media.decode().then(reveal, reveal);
    } else {
      reveal();
    }
    const preload = ids[(index + 1) % ids.length];
    const pre = state.byId.get(preload);
    if (pre && pre.kind === "image") new Image().src = stillUrl(pre, 2048);
    schedule();
  }

  function schedule(): void {
    window.clearTimeout(timer);
    if (playing) timer = window.setTimeout(() => show(index + 1), interval);
  }

  function end(): void {
    window.clearTimeout(timer);
    music.stop();
    window.removeEventListener("keydown", keys, true);
    root.classList.remove("open");
    setTimeout(() => root.remove(), 260);
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
  }

  const keys = (event: KeyboardEvent) => {
    event.stopPropagation();
    if (event.key === "Escape") end();
    else if (event.key === "ArrowRight") show(index + 1);
    else if (event.key === "ArrowLeft") show(index - 1);
    else if (event.key === " ") { event.preventDefault(); playBtn.click(); }
  };
  window.addEventListener("keydown", keys, true);
  close.addEventListener("click", end);
  prev.addEventListener("click", () => show(index - 1));
  next.addEventListener("click", () => show(index + 1));
  playBtn.addEventListener("click", () => {
    playing = !playing;
    setPlayIcon();
    if (playing) { schedule(); startMusic(); } else { window.clearTimeout(timer); music.stop(); }
  });
  theme.addEventListener("change", startMusic);
  speed.addEventListener("change", () => { interval = Number(speed.value); schedule(); });
  root.style.setProperty("--ss-fade", "1.2s");
  setPlayIcon();
  void root.requestFullscreen?.().catch(() => undefined);
  void Promise.all(ids.filter((id) => !state.byId.has(id)).slice(0, 400).map((id) => api<Media>(`/media/${id}`).then((m) => state.byId.set(id, m)).catch(() => undefined)))
    .then(() => { startMusic(); show(index); });
}

export function openCompare(ids: number[]): void {
  if (ids.length < 2 || document.querySelector(".compare")) return;
  const chosen = ids.slice(0, 4);
  let scale = 1;
  let tx = 0;
  let ty = 0;
  let linked = true;
  let focus = 0;
  const panes = chosen.map((id) => {
    const img = h("img", { class: "cmp-img", alt: "", draggable: false }) as HTMLImageElement;
    const item = state.byId.get(id);
    img.src = item ? stillUrl(item, 3072) : thumbUrl(id, 768);
    const label = h("div", { class: "cmp-label" }, item?.name ?? String(id));
    const stars = h("div", { class: "cmp-stars" }, "");
    const pane = h("div", { class: "cmp-pane" }, h("div", { class: "cmp-inner" }, img), label, stars);
    return { id, pane, img, stars, own: { scale: 1, tx: 0, ty: 0 } };
  });
  const paint = () => panes.forEach((p, i) => {
    const t = linked ? { scale, tx, ty } : p.own;
    p.img.style.transform = `translate(${t.tx}px, ${t.ty}px) scale(${t.scale})`;
    p.pane.classList.toggle("focus", i === focus);
    const item = state.byId.get(p.id);
    setText(p.stars, item ? `${"★".repeat(item.rating ?? 0)}${item.rejected ? " Rejected" : ""}${item.favorite ? " Favorite" : ""}` : "");
  });
  const linkBtn = h("button", { class: "btn", type: "button" }, "Linked Zoom: On");
  const fit = h("button", { class: "btn", type: "button" }, "Fit");
  const one = h("button", { class: "btn", type: "button" }, "100%");
  const close = h("button", { class: "icon-btn", type: "button", "aria-label": "Close compare" }, iconEl("close"));
  const grid = h("div", { class: `cmp-grid n${chosen.length}` }, ...panes.map((p) => p.pane));
  const root = h("div", { class: "compare" }, h("div", { class: "ed-top" }, close, h("span", { class: "ed-title" }, `Compare ${chosen.length} items`), h("span", { class: "head-spacer" }),
    h("span", { class: "field-hint" }, "Scroll to zoom, drag to pan, 0-5 to rate, X to reject, click a pane to focus"), linkBtn, fit, one), grid);
  document.body.append(root);
  requestAnimationFrame(() => root.classList.add("open"));
  const target = (i: number) => (linked ? null : panes[i].own);
  panes.forEach((p, i) => {
    p.pane.addEventListener("wheel", (event) => {
      event.preventDefault();
      focus = i;
      const t = target(i) ?? { scale, tx, ty };
      const rect = p.pane.getBoundingClientRect();
      const cx = event.clientX - rect.left - rect.width / 2;
      const cy = event.clientY - rect.top - rect.height / 2;
      const nextScale = Math.min(12, Math.max(1, t.scale * Math.exp(-event.deltaY * 0.0025)));
      const k = nextScale / t.scale;
      t.tx = cx - (cx - t.tx) * k;
      t.ty = cy - (cy - t.ty) * k;
      t.scale = nextScale;
      if (nextScale === 1) { t.tx = 0; t.ty = 0; }
      if (linked) ({ scale, tx, ty } = t);
      paint();
    }, { passive: false });
    p.pane.addEventListener("pointerdown", (event) => {
      focus = i;
      p.pane.setPointerCapture(event.pointerId);
      const t = target(i) ?? { scale, tx, ty };
      const sx = event.clientX - t.tx;
      const sy = event.clientY - t.ty;
      const move = (ev: PointerEvent) => {
        t.tx = ev.clientX - sx;
        t.ty = ev.clientY - sy;
        if (linked) ({ scale, tx, ty } = t);
        paint();
      };
      const up = () => { p.pane.removeEventListener("pointermove", move); p.pane.removeEventListener("pointerup", up); };
      p.pane.addEventListener("pointermove", move);
      p.pane.addEventListener("pointerup", up);
      paint();
    });
  });
  linkBtn.addEventListener("click", () => {
    linked = !linked;
    if (!linked) panes.forEach((p) => { p.own = { scale, tx, ty }; });
    setText(linkBtn, `Linked Zoom: ${linked ? "On" : "Off"}`);
    paint();
  });
  fit.addEventListener("click", () => { scale = 1; tx = 0; ty = 0; panes.forEach((p) => { p.own = { scale: 1, tx: 0, ty: 0 }; }); paint(); });
  one.addEventListener("click", () => {
    const p = panes[focus];
    const s = p.img.naturalWidth / Math.max(1, p.img.clientWidth);
    scale = Math.max(1, s);
    tx = 0;
    ty = 0;
    panes.forEach((x) => { x.own = { scale, tx: 0, ty: 0 }; });
    paint();
  });
  const end = () => {
    window.removeEventListener("keydown", keys, true);
    root.classList.remove("open");
    setTimeout(() => root.remove(), 200);
  };
  close.addEventListener("click", end);
  const keys = (event: KeyboardEvent) => {
    event.stopPropagation();
    const id = panes[focus].id;
    if (event.key === "Escape") end();
    else if (/^[0-5]$/.test(event.key)) void saveMeta([id], { rating: Number(event.key) }).then(paint);
    else if (event.key.toLowerCase() === "x") void saveMeta([id], { rejected: !state.byId.get(id)?.rejected }).then(paint);
    else if (event.key === ".") void saveMeta([id], { favorite: !state.byId.get(id)?.favorite }).then(paint);
    else if (event.key === "ArrowRight") { focus = (focus + 1) % panes.length; paint(); }
    else if (event.key === "ArrowLeft") { focus = (focus - 1 + panes.length) % panes.length; paint(); }
  };
  window.addEventListener("keydown", keys, true);
  paint();
}

async function createMemoryFlow(ids: number[]): Promise<void> {
  const title = await promptText("Create Memory", "My Memory", `${countFmt(ids.length)} items`, "Create");
  if (!title) return;
  const res = await api<{ id: number }>("/memories", { method: "POST", body: JSON.stringify({ ids, title }) });
  navigate(`#/memory/${res.id}`);
}

let registered = false;

export function registerCurate(): void {
  if (registered) return;
  registered = true;
  selectbarExtras.push(
    { label: "Compare", icon: "compare", handler: (ids) => { if (ids.length >= 2) openCompare(ids); else toast("Select 2 to 4 items to compare"); } },
    { label: "Slideshow", icon: "slideshow", handler: (ids) => openSlideshow(ids) },
  );
  tileHooks.ctx.push((item) => {
    const ids = state.selection.has(item.id) && state.selection.size > 1 ? [...state.selection] : [item.id];
    const entries: CtxEntry[] = [{ label: "Create Memory...", icon: "memory", action: () => void createMemoryFlow(ids) }];
    if (state.route.view === "memory") {
      const memoryId = Number(state.route.param);
      entries.push({ label: "Remove from Memory", icon: "minus", action: async () => {
        await api(`/memories/${memoryId}/remove`, { method: "POST", body: JSON.stringify({ ids }) });
        invalidateMedia();
        emitTopic("media");
        toast(`Removed ${countFmt(ids.length)} from this memory`);
      } });
    }
    if (ids.length >= 2) entries.push({ label: "Compare", icon: "compare", action: () => openCompare(ids) });
    return entries;
  });
  viewerHooks.toolbar.push(() => {
    const btn = h("button", { class: "icon-btn", type: "button", "aria-label": "Slideshow" }, iconEl("slideshow"));
    btn.addEventListener("click", () => {
      if (!state.viewer) return;
      openSlideshow([...state.viewer.ids], { start: state.viewer.index });
    });
    return btn;
  });
}
