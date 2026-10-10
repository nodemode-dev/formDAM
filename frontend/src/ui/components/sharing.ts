import { api } from "../../engine/api.js";
import { countFmt, fullStamp } from "../../engine/format.js";
import { invalidateMedia, pollJob, state } from "../../engine/store.js";
import type { CtxEntry } from "../contextmenu.js";
import { openContextMenu } from "../contextmenu.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { promptText } from "../prompt.js";
import { toast } from "../toast.js";
import { tileHooks } from "./grid.js";
import { pickFolder } from "./outputs.js";
import { selectbarExtras } from "./selectbar.js";
import { mountPackageList, openPackageFlow, packageFlow } from "./packages.js";
import { viewerHooks } from "./viewer.js";

export async function galleryFlow(ids: number[]): Promise<void> {
  const title = await promptText("Web Gallery", "Web Gallery", "A folder with an index.html you can open or upload to any web host");
  if (!title) return;
  const dest = await pickFolder("Save the gallery in");
  if (!dest) return;
  const res = await api<{ job_id: string }>("/packages/gallery", { method: "POST", body: JSON.stringify({ ids, title, dest }) });
  pollJob(res.job_id, (job) => toast(`Web gallery written with ${countFmt(job.counts.written ?? 0)} item${(job.counts.written ?? 0) === 1 ? "" : "s"}${job.counts.skipped ? `, ${countFmt(job.counts.skipped)} private or unreadable skipped` : ""}`));
}

async function moveLibrary(ids: number[], shared: boolean): Promise<void> {
  try {
    const res = await api<{ changed: number; skipped: number }>("/media/shared-library", { method: "POST", body: JSON.stringify({ ids, shared }) });
    invalidateMedia();
    const sync = await api<SyncState>("/sync").catch(() => null);
    const off = shared && !sync?.channels.shared.enabled ? ". Turn on the Shared Library on the Sharing page so family members on your network receive them" : "";
    toast(`${countFmt(res.changed)} moved to the ${shared ? "Shared" : "Personal"} Library${res.skipped ? `, ${countFmt(res.skipped)} skipped (private, hidden, already there or added by someone else)` : ""}${off}`);
  } catch (err) {
    toast((err as Error).message, "error");
  }
}

function shareEntries(ids: number[]): CtxEntry[] {
  return [
    { label: "Share as Encrypted Package...", icon: "lock", action: () => void packageFlow(ids) },
    { label: "Web Gallery...", icon: "browser", action: () => void galleryFlow(ids) },
  ];
}

interface SyncChannel {
  channel: "personal" | "shared"; folder: string; enabled: boolean; last_push: number; last_pull: number; error?: string | null; ts?: number;
  pushed?: { media: number; objects: number; albums: number }; pulled?: { applied: number; imported: number; waiting: number };
  devices: Array<{ id: string; name: string; seen: number; me: boolean }>;
}
interface SyncState { device: { id: string; name: string }; channels: Record<"personal" | "shared", SyncChannel> }

function syncCard(channel: "personal" | "shared", heading: string, hint: string, onState: (s: SyncState) => void): { el: HTMLElement; paint: (s: SyncState) => void } {
  const enabled = h("input", { type: "checkbox" }) as HTMLInputElement;
  const folder = h("span", { class: "sync-folder" }, "");
  const choose = h("button", { class: "btn", type: "button" }, "Choose Folder...");
  const now = h("button", { class: "btn", type: "button" }, iconEl("sync"), "Sync Now");
  const status = h("p", { class: "field-hint" }, "");
  const peers = h("p", { class: "field-hint" }, "");
  const el = h("div", { class: "share-settings glass-panel" },
    h("div", { class: "sync-head" }, h("b", {}, heading)), h("p", { class: "field-hint" }, hint),
    h("label", { class: "field-check" }, enabled, "On"), h("div", { class: "row-gap" }, choose, now), folder, status, peers);
  const later = () => { for (const ms of [2500, 8000]) window.setTimeout(() => void api<SyncState>("/sync").then(onState).catch(() => undefined), ms); };
  const put = async (body: Record<string, unknown>) => {
    try {
      onState(await api<SyncState>(`/sync/${channel}`, { method: "PUT", body: JSON.stringify(body) }));
      later();
    } catch (err) {
      toast((err as Error).message, "error");
      onState(await api<SyncState>("/sync"));
    }
  };
  enabled.addEventListener("change", () => void put({ enabled: enabled.checked }));
  choose.addEventListener("click", async () => {
    const picked = await pickFolder(channel === "shared" ? "Shared Library folder" : "Sync folder");
    if (picked) void put({ folder: picked, enabled: true });
  });
  now.addEventListener("click", () => void api("/sync/now", { method: "POST" }).then(() => { toast("Syncing"); later(); }));
  const paint = (s: SyncState) => {
    const c = s.channels[channel];
    enabled.checked = c.enabled;
    setText(folder, c.folder ? `Folder: ${c.folder}` : "No folder chosen");
    now.classList.toggle("hidden", !c.enabled);
    let line = c.enabled ? "Waiting for the first pass" : "Off";
    if (c.error) line = `Problem: ${c.error}`;
    else if (c.ts && c.pushed && c.pulled) line = `Last pass ${fullStamp(c.ts)}: sent ${countFmt(c.pushed.media)}, received ${countFmt(c.pulled.imported)} new & ${countFmt(c.pulled.applied)} changes${c.pulled.waiting ? `, ${c.pulled.waiting} still arriving` : ""}`;
    setText(status, line);
    const others = c.devices.filter((d) => !d.me);
    setText(peers, others.length ? `${channel === "shared" ? "Participants" : "Other devices"}: ${others.map((d) => `${d.name} (seen ${fullStamp(d.seen)})`).join(", ")}` : "");
  };
  return { el, paint };
}

interface FamilyPeer { dev: string; name: string; ip: string; port: number; seen: number; synced?: number; manual: boolean }
interface FamilyState { enabled: boolean; has_key: boolean; port: number; family_id: string; running: boolean; peers: FamilyPeer[]; status: SyncChannel }

function familyCard(): { el: HTMLElement; paint: (f: FamilyState) => void } {
  const enabled = h("input", { type: "checkbox" }) as HTMLInputElement;
  const fid = h("p", { class: "field-hint" }, "");
  const keyBox = h("div", { class: "pkg-password hidden" }, "");
  const showKey = h("button", { class: "btn", type: "button" }, "Show Key");
  const newKey = h("button", { class: "btn", type: "button" }, "New Key");
  const paste = h("input", { class: "field-input", type: "text", placeholder: "Paste a key from another family member", spellcheck: "false", autocomplete: "off" }) as HTMLInputElement;
  const usePaste = h("button", { class: "btn", type: "button" }, "Use Key");
  const port = h("input", { class: "field-input compact", type: "number", min: "1024", max: "65535" }) as HTMLInputElement;
  const address = h("input", { class: "field-input", type: "text", placeholder: "192.168.1.20:8792", spellcheck: "false" }) as HTMLInputElement;
  const addPeer = h("button", { class: "btn", type: "button" }, "Add Device");
  const peers = h("div", { class: "share-activity" });
  const status = h("p", { class: "field-hint" }, "");
  const error = h("p", { class: "field-error" }, "");
  for (const input of [paste, port, address]) input.addEventListener("keydown", (event) => event.stopPropagation());
  const el = h("div", { class: "share-settings glass-panel" },
    h("div", { class: "sync-head" }, h("b", {}, "Shared Library")),
    h("p", { class: "field-hint" }, "A second library shared with family, only over your local network and only between DAM apps that hold the same share key. Nothing goes through a cloud or the internet: each app answers its family members directly, every request is signed with the key and every reply is encrypted with it. Off until you turn it on. Move photos in from the photo menu; everyone sees, edits & deletes them, and only the person who added a photo can move it back to Personal."),
    h("label", { class: "field-check" }, enabled, "On (this computer takes part)"), fid, keyBox,
    h("div", { class: "row-gap" }, showKey, newKey),
    h("div", { class: "row-gap pkg-pw-row" }, paste, usePaste),
    h("div", { class: "row-gap pkg-pw-row" }, h("label", { class: "field" }, h("span", { class: "field-label" }, "Port"), port)),
    h("div", { class: "row-gap pkg-pw-row" }, address, addPeer), peers, status, error);
  const fail = (err: unknown) => setText(error, (err as { detail?: string }).detail ?? (err as Error).message);
  const reload = async () => paint(await api<FamilyState>("/family"));
  enabled.addEventListener("change", async () => {
    setText(error, "");
    try { paint(await api<FamilyState>("/family", { method: "PUT", body: JSON.stringify({ enabled: enabled.checked }) })); } catch (err) { fail(err); void reload(); }
  });
  port.addEventListener("change", async () => {
    setText(error, "");
    try { paint(await api<FamilyState>("/family", { method: "PUT", body: JSON.stringify({ port: Number(port.value) }) })); } catch (err) { fail(err); void reload(); }
  });
  showKey.addEventListener("click", async () => {
    if (!keyBox.classList.contains("hidden")) { keyBox.classList.add("hidden"); setText(showKey, "Show Key"); return; }
    const res = await api<{ key: string }>("/family/key");
    setText(keyBox, res.key || "No key yet");
    keyBox.classList.remove("hidden");
    setText(showKey, "Hide Key");
  });
  const setKey = async (key: string | null) => {
    setText(error, "");
    try {
      const res = await api<{ key: string }>("/family/key", { method: "POST", body: JSON.stringify(key ? { key } : {}) });
      setText(keyBox, res.key);
      keyBox.classList.remove("hidden");
      setText(showKey, "Hide Key");
      paste.value = "";
      await reload();
    } catch (err) { fail(err); }
  };
  newKey.addEventListener("click", () => void setKey(null));
  usePaste.addEventListener("click", () => { if (paste.value.trim()) void setKey(paste.value.trim()); });
  addPeer.addEventListener("click", async () => {
    setText(error, "");
    try { await api("/family/peers", { method: "POST", body: JSON.stringify({ address: address.value.trim() }) }); address.value = ""; await reload(); } catch (err) { fail(err); }
  });
  function paint(f: FamilyState): void {
    enabled.checked = f.enabled;
    if (document.activeElement !== port) port.value = String(f.port);
    setText(fid, f.has_key ? `Family ID ${f.family_id}: every member sees the same ID when they hold the same key. Share the key in person or by a channel you trust.` : "No share key yet: create one here, or paste the key another family member shows you.");
    for (const b of [newKey, usePaste]) b.toggleAttribute("disabled", f.enabled);
    paste.toggleAttribute("disabled", f.enabled);
    patchList(peers, f.peers, (p) => p.dev, (p) => h("div", { class: "share-act" }, h("b", {}, p.name || "DAM"), ` · ${p.ip}:${p.port}`, h("span", { class: "list-sub" }, "")),
      (node, p) => setText(node.lastElementChild as HTMLElement, ` · ${p.synced ? `synced ${fullStamp(p.synced)}` : `seen ${fullStamp(p.seen)}`}`));
    const s = f.status;
    let line = f.enabled ? (f.peers.length ? "Waiting for the first pass" : "Looking for family members on this network") : "Off";
    if (f.enabled && s.error) line = `Problem: ${s.error}`;
    else if (f.enabled && s.ts && s.pulled) line = `Last pass ${fullStamp(s.ts)}: received ${countFmt(s.pulled.imported)} new & ${countFmt(s.pulled.applied)} changes from ${countFmt(f.peers.length)} member${f.peers.length === 1 ? "" : "s"}`;
    setText(status, line);
  }
  return { el, paint };
}

export function mountSharedPage(host: HTMLElement): () => void {
  const packagesBox = h("div", {});
  const openInput = h("input", { type: "file", accept: ".zip,application/zip", class: "hidden" }) as HTMLInputElement;
  const openBtn = h("button", { class: "btn", type: "button" }, iconEl("upload"), "Open Package...");
  openBtn.addEventListener("click", () => openInput.click());
  openInput.addEventListener("change", () => {
    const file = openInput.files?.[0];
    openInput.value = "";
    if (file) void openPackageFlow(file).then((ok) => { if (!ok) toast("That file is not a DAM share package", "error"); });
  });
  const deviceName = h("input", { class: "field-input compact", type: "text", maxlength: "60" }) as HTMLInputElement;
  let paintSync: (s: SyncState) => void = () => undefined;
  const personal = syncCard("personal", "Sync This Library", "Keeps this library the same on your other computers through a folder they all see: iCloud Drive, Dropbox, OneDrive, Syncthing, a NAS or an external drive. Originals (with Live Photo videos), edits, trims, favorites, ratings, keywords, captions, locations, plain albums & deletions sync; people, smart albums, stacks & memories stay per computer. Private, hidden & vaulted items are never written to the folder, and making a synced photo private, hidden or vaulted removes its file from the folder & hides it on the other computers.", (s) => paintSync(s));
  const family = familyCard();
  paintSync = (s) => { personal.paint(s); if (document.activeElement !== deviceName) deviceName.value = s.device.name; };
  deviceName.addEventListener("change", () => void api<SyncState>("/sync/device", { method: "PUT", body: JSON.stringify({ name: deviceName.value || "This computer" }) }).then(paintSync));
  const pad = h("div", { class: "view-pad" },
    h("div", { class: "section-head" }, h("h2", {}, "Encrypted Packages"), h("span", { class: "head-spacer" }), openBtn, openInput),
    h("p", { class: "field-hint pkg-lede" }, "Sharing in DAM never opens a server. A package is an AES-256 encrypted zip with scrambled file names: send it any way you like, give the password separately, and the other person drops it into DAM. Album packages keep a shared album in step in both directions, with notes."),
    packagesBox,
    h("div", { class: "section-head" }, h("h2", {}, "Sync & Shared Library")),
    h("label", { class: "field sync-device" }, h("span", { class: "field-label" }, "This computer is called"), deviceName),
    h("div", { class: "sync-cards" }, personal.el, family.el));
  host.append(pad);
  let alive = true;
  const unmountPackages = mountPackageList(packagesBox);

  async function refresh(): Promise<void> {
    const [sync, fam] = await Promise.all([api<SyncState>("/sync"), api<FamilyState>("/family")]);
    if (!alive) return;
    paintSync(sync);
    family.paint(fam);
  }
  void refresh();
  const timer = window.setInterval(() => void refresh(), 15000);
  return () => { alive = false; unmountPackages(); window.clearInterval(timer); };
}

let registered = false;

export function registerSharing(): void {
  if (registered) return;
  registered = true;
  selectbarExtras.push({ label: "Share", icon: "share", handler: (ids) => {
    if (!ids.length) return;
    const bar = document.querySelector<HTMLElement>(".sel-bar");
    const rect = bar?.getBoundingClientRect();
    openContextMenu(rect ? rect.left + 160 : 200, rect ? rect.top - 160 : 200, shareEntries(ids));
  } });
  tileHooks.ctx.push((item) => {
    const ids = state.selection.has(item.id) && state.selection.size > 1 ? [...state.selection] : [item.id];
    const inShared = Boolean((item as { shared_lib?: number }).shared_lib);
    return [{ label: "Share as Encrypted Package...", icon: "lock", action: () => void packageFlow(ids) },
      { label: "Web Gallery...", icon: "browser", action: () => void galleryFlow(ids) },
      { label: inShared ? "Move to Personal Library" : "Move to Shared Library", icon: "shared", action: () => void moveLibrary(ids, !inShared) }];
  });
  viewerHooks.toolbar.push((current) => {
    const btn = h("button", { class: "icon-btn", type: "button", "aria-label": "Share" }, iconEl("share"));
    btn.addEventListener("click", () => {
      const id = current();
      if (id === null) return;
      const rect = btn.getBoundingClientRect();
      openContextMenu(rect.left - 160, rect.bottom + 6, shareEntries([id]));
    });
    return btn;
  });
}
