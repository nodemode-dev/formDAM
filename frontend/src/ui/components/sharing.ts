import { api } from "../../engine/api.js";
import { countFmt, fullStamp } from "../../engine/format.js";
import { pollJob, state } from "../../engine/store.js";
import type { CtxEntry } from "../contextmenu.js";
import { openContextMenu } from "../contextmenu.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { openModal, textField } from "../modal.js";
import { promptText } from "../prompt.js";
import { toast } from "../toast.js";
import { tileHooks } from "./grid.js";
import { pickFolder } from "./outputs.js";
import { selectbarExtras } from "./selectbar.js";
import { viewerHooks } from "./viewer.js";

interface ShareSettings { enabled: boolean; port: number; name: string; running: boolean; urls: string[]; native: boolean }

interface Share {
  id: number; token: string; kind: "link" | "album"; album_id: number | null; album_name?: string | null; title: string;
  created_ts: number; expires_ts: number | null; has_password: boolean; allow_download: number; allow_comments: number;
  allow_contrib: number; include_location: number; views: number; url: string; count: number; unread: number;
}

interface Activity { id: number; media_id: number | null; kind: string; author: string; text: string | null; ts: number; owner: number }

let native = false;

function check(label: string, on: boolean): { wrap: HTMLElement; input: HTMLInputElement } {
  const input = h("input", { type: "checkbox" }) as HTMLInputElement;
  input.checked = on;
  return { wrap: h("label", { class: "field-check" }, input, label), input };
}

function serverNotice(settings: ShareSettings): HTMLElement {
  const text = h("p", { class: "field-hint" }, "");
  const turnOn = h("button", { class: "btn", type: "button" }, "Turn On Sharing");
  const box = h("div", { class: "share-note" }, text, turnOn);
  const paint = (s: ShareSettings) => {
    setText(text, s.running
      ? `Sharing is on. People on your network, or on a VPN such as Tailscale that reaches this computer, can open the link while DAM is running.`
      : `Sharing is off. Turning it on starts a small guest server on port ${s.port} that only answers share links; the rest of DAM stays private to this computer.`);
    turnOn.classList.toggle("hidden", s.running);
  };
  turnOn.addEventListener("click", async () => {
    try {
      paint(await api<ShareSettings>("/sharing/settings", { method: "PUT", body: JSON.stringify({ enabled: true }) }));
    } catch (err) {
      toast((err as Error).message, "error");
    }
  });
  paint(settings);
  return box;
}

function resultPanel(share: Share): HTMLElement {
  const url = h("input", { class: "field-input", readonly: "true", value: share.url }) as HTMLInputElement;
  const copy = h("button", { class: "btn", type: "button" }, iconEl("copy"), "Copy Link");
  copy.addEventListener("click", () => void navigator.clipboard?.writeText(share.url).then(() => toast("Link copied")).catch(() => url.select()));
  const qr = h("img", { class: "share-qr", src: `/api/sharing/${share.id}/qr.png`, width: "180", height: "180", alt: "QR code for the link" });
  const actions = h("div", { class: "row-gap" }, copy);
  const sendBtn = (service: string, label: string) => {
    const btn = h("button", { class: "btn", type: "button" }, label);
    btn.addEventListener("click", () => void api("/sharing/send", { method: "POST", body: JSON.stringify({ service, share_id: share.id }) })
      .catch((err) => toast((err as Error).message, "error")));
    return btn;
  };
  actions.append(sendBtn("mail", "Mail Link"));
  if (native) actions.append(sendBtn("messages", "Messages"), sendBtn("airdrop", "AirDrop"));
  const facts = [`${countFmt(share.count)} item${share.count === 1 ? "" : "s"}`];
  if (share.expires_ts) facts.push(`expires ${fullStamp(share.expires_ts)}`);
  if (share.has_password) facts.push("password protected");
  if (!share.include_location) facts.push("location removed");
  return h("div", { class: "share-result" }, h("p", { class: "field-hint" }, facts.join(" · ")), url, actions, qr);
}

async function shareForm(heading: string, initialTitle: string, album: boolean, submit: (body: Record<string, unknown>) => Promise<Share>): Promise<void> {
  const settings = await api<ShareSettings>("/sharing/settings");
  native = settings.native;
  const modal = openModal(heading, 460);
  const title = textField("Title", "text", "Shared Photos");
  title.input.value = initialTitle;
  const expiry = h("select", { class: "field-input" },
    h("option", { value: "" }, "Never expires"), h("option", { value: "1" }, "1 day"), h("option", { value: "7" }, "7 days"),
    h("option", { value: "30" }, "30 days"), h("option", { value: "365" }, "1 year")) as HTMLSelectElement;
  const password = textField("Password (optional)", "password", "Anyone with the link can view");
  const download = check("Allow downloads", true);
  const comments = check("Allow comments and likes", true);
  const contrib = check("Let people add photos and videos", false);
  const location = check("Include location", false);
  const create = h("button", { class: "btn primary", type: "button" }, album ? "Share Album" : "Create Link");
  const form = h("div", { class: "share-form" }, serverNotice(settings), title.wrap,
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Expires"), expiry), password.wrap,
    download.wrap, comments.wrap, album ? contrib.wrap : h("span", { class: "hidden" }), location.wrap,
    h("p", { class: "field-hint" }, "Private, hidden and deleted items are never shared. Edited photos are shared as edited."),
    h("div", { class: "row-gap" }, create));
  create.addEventListener("click", async () => {
    create.setAttribute("disabled", "true");
    try {
      const share = await submit({
        title: title.input.value.trim(), expires_days: expiry.value ? Number(expiry.value) : null, password: password.input.value || null,
        allow_download: download.input.checked, allow_comments: comments.input.checked, allow_contrib: contrib.input.checked,
        include_location: location.input.checked,
      });
      modal.body.replaceChildren(resultPanel(share));
      void refreshShared?.();
    } catch (err) {
      create.removeAttribute("disabled");
      toast((err as Error).message, "error");
    }
  });
  modal.body.append(form);
}

export function shareLinkFlow(ids: number[]): Promise<void> {
  const first = state.byId.get(ids[0]);
  return shareForm("Share Link", ids.length === 1 && first?.title ? first.title : "Shared Photos", false,
    (body) => api<Share>("/sharing/links", { method: "POST", body: JSON.stringify({ ...body, ids }) }));
}

export function shareAlbumFlow(albumId: number, name: string): Promise<void> {
  return shareForm("Share Album", name, true,
    (body) => api<Share>(`/sharing/albums/${albumId}`, { method: "POST", body: JSON.stringify(body) }));
}

async function sendFiles(ids: number[], service: string): Promise<void> {
  try {
    await api("/sharing/send", { method: "POST", body: JSON.stringify({ service, ids }) });
  } catch (err) {
    toast((err as Error).message, "error");
  }
}

export async function galleryFlow(ids: number[]): Promise<void> {
  const title = await promptText("Web Gallery", "Web Gallery", "A folder with an index.html you can open or upload to any web host");
  if (!title) return;
  const dest = await pickFolder("Save the gallery in");
  if (!dest) return;
  const res = await api<{ job_id: string }>("/sharing/gallery", { method: "POST", body: JSON.stringify({ ids, title, dest }) });
  pollJob(res.job_id, (job) => toast(`Web gallery written with ${countFmt(job.counts.written ?? 0)} item${(job.counts.written ?? 0) === 1 ? "" : "s"}${job.counts.skipped ? `, ${countFmt(job.counts.skipped)} private or unreadable skipped` : ""}`));
}

function shareEntries(ids: number[]): CtxEntry[] {
  const entries: CtxEntry[] = [
    { label: "Share Link...", icon: "link", action: () => void shareLinkFlow(ids) },
    { label: "Web Gallery...", icon: "browser", action: () => void galleryFlow(ids) },
  ];
  if (native) {
    entries.push("sep",
      { label: "Mail", icon: "note", action: () => void sendFiles(ids, "mail") },
      { label: "Messages", icon: "note", action: () => void sendFiles(ids, "messages") },
      { label: "AirDrop", icon: "share", action: () => void sendFiles(ids, "airdrop") });
  }
  return entries;
}

let refreshShared: (() => Promise<void>) | null = null;

export function mountSharedPage(host: HTMLElement): () => void {
  const enabled = h("input", { type: "checkbox" }) as HTMLInputElement;
  const port = h("input", { class: "field-input compact", type: "number", min: "1024", max: "65535" }) as HTMLInputElement;
  const name = h("input", { class: "field-input compact", type: "text", maxlength: "60" }) as HTMLInputElement;
  const urls = h("p", { class: "field-hint" }, "");
  const settingsCard = h("div", { class: "share-settings glass-panel" },
    h("label", { class: "field-check" }, enabled, "Sharing on (guest server for share links)"),
    h("div", { class: "row-gap" }, h("label", { class: "field" }, h("span", { class: "field-label" }, "Port"), port),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Shown to guests as"), name)), urls);
  const list = h("div", { class: "list-rows" });
  const empty = h("p", { class: "field-hint" }, "Nothing shared yet. Select photos and choose Share, or open an album and choose Share Album.");
  const actHead = h("div", { class: "section-head" }, h("h2", {}, "Activity"));
  const actList = h("div", { class: "share-activity" });
  const reply = h("textarea", { class: "field-input", rows: "2", placeholder: "Reply as the owner" }) as HTMLTextAreaElement;
  const send = h("button", { class: "btn", type: "button" }, "Post");
  const actEmpty = h("p", { class: "field-hint hidden" }, "No comments, likes or additions yet.");
  const actPane = h("div", { class: "share-act-pane hidden" }, actHead, actEmpty, actList, reply, h("div", { class: "row-gap" }, send));
  const pad = h("div", { class: "view-pad" },
    h("div", { class: "section-head" }, h("h2", {}, "Guest Server")), settingsCard,
    h("div", { class: "section-head" }, h("h2", {}, "Shared Links & Albums")), empty, list, actPane);
  host.append(pad);
  let alive = true;
  let selected: number | null = null;

  function paintSettings(s: ShareSettings): void {
    enabled.checked = s.enabled;
    if (document.activeElement !== port) port.value = String(s.port);
    if (document.activeElement !== name) name.value = s.name;
    setText(urls, s.running ? `Guests reach this computer at ${s.urls.join(" or ")}` : "Off. Share links stop working until sharing is on again.");
  }

  async function putSettings(body: Record<string, unknown>): Promise<void> {
    try {
      paintSettings(await api<ShareSettings>("/sharing/settings", { method: "PUT", body: JSON.stringify(body) }));
    } catch (err) {
      toast((err as Error).message, "error");
      paintSettings(await api<ShareSettings>("/sharing/settings"));
    }
  }
  enabled.addEventListener("change", () => void putSettings({ enabled: enabled.checked }));
  port.addEventListener("change", () => void putSettings({ port: Number(port.value) }));
  name.addEventListener("change", () => void putSettings({ name: name.value }));

  function row(s: Share): HTMLElement {
    const titleEl = h("div", { class: "list-title" }, s.title);
    const sub = h("div", { class: "list-sub" }, "");
    const badge = h("span", { class: "share-unread hidden" }, "");
    const copy = h("button", { class: "btn", type: "button" }, "Copy Link");
    copy.addEventListener("click", (e) => { e.stopPropagation(); void navigator.clipboard?.writeText(s.url).then(() => toast("Link copied")); });
    const more = h("button", { class: "icon-btn", type: "button", "aria-label": "More" }, iconEl("dot"));
    more.addEventListener("click", (e) => {
      e.stopPropagation();
      const rect = more.getBoundingClientRect();
      openContextMenu(rect.left - 160, rect.bottom + 6, [
        { label: "Show QR Code", icon: "qr", action: () => { const m = openModal(s.title, 260); m.body.append(h("img", { class: "share-qr", src: `/api/sharing/${s.id}/qr.png`, width: "200", height: "200", alt: "QR code" })); } },
        { label: "Mail Link", icon: "note", action: () => void api("/sharing/send", { method: "POST", body: JSON.stringify({ service: "mail", share_id: s.id }) }).catch((err) => toast((err as Error).message, "error")) },
        "sep",
        { label: s.kind === "album" ? "Stop Sharing Album" : "Turn Off Link", icon: "close", danger: true, action: async () => {
          await api(`/sharing/${s.id}`, { method: "DELETE" });
          if (selected === s.id) { selected = null; actPane.classList.add("hidden"); }
          void refresh();
        } },
      ]);
    });
    const node = h("div", { class: "list-row glass-panel share-row", role: "button", tabindex: "0" },
      h("span", { class: "list-thumb share-kind" }, iconEl(s.kind === "album" ? "albums" : "link")),
      h("div", { class: "list-main" }, titleEl, sub), badge, copy, more);
    node.addEventListener("click", () => void openActivity(s.id));
    paintRow(node, s);
    return node;
  }

  function paintRow(node: HTMLElement, s: Share): void {
    const sub = node.querySelector(".list-sub") as HTMLElement;
    const parts = [s.kind === "album" ? `Shared album${s.album_name ? ` (${s.album_name})` : ""}` : "Link",
      `${countFmt(s.count)} item${s.count === 1 ? "" : "s"}`, `${countFmt(s.views)} view${s.views === 1 ? "" : "s"}`];
    if (s.has_password) parts.push("password");
    if (s.expires_ts) parts.push(s.expires_ts < Date.now() / 1000 ? "expired" : `until ${fullStamp(s.expires_ts)}`);
    setText(sub, parts.join(" · "));
    const badge = node.querySelector(".share-unread") as HTMLElement;
    setText(badge, s.unread ? `${s.unread} new` : "");
    badge.classList.toggle("hidden", !s.unread);
    node.classList.toggle("active", selected === s.id);
  }

  async function openActivity(id: number): Promise<void> {
    selected = id;
    const data = await api<{ share: Share; activity: Activity[] }>(`/sharing/${id}/activity`);
    if (!alive || selected !== id) return;
    setText(actHead.firstElementChild as HTMLElement, `Activity · ${data.share.title}`);
    patchList(actList, data.activity, (a) => String(a.id), (a) => h("div", { class: "share-act" },
      h("b", {}, `${a.author}${a.owner ? " (you)" : ""}`),
      a.kind === "like" ? " liked a photo" : a.kind === "contrib" ? " added a photo" : `: ${a.text ?? ""}`,
      h("span", { class: "list-sub" }, ` · ${fullStamp(a.ts)}`)));
    actEmpty.classList.toggle("hidden", data.activity.length > 0);
    actPane.classList.remove("hidden");
    void refresh();
  }

  send.addEventListener("click", async () => {
    if (selected === null || !reply.value.trim()) return;
    try {
      await api(`/sharing/${selected}/comment`, { method: "POST", body: JSON.stringify({ text: reply.value.trim() }) });
      reply.value = "";
      void openActivity(selected);
    } catch (err) {
      toast((err as Error).message, "error");
    }
  });

  async function refresh(): Promise<void> {
    const [s, data] = await Promise.all([api<ShareSettings>("/sharing/settings"), api<{ shares: Share[] }>("/sharing")]);
    if (!alive) return;
    native = s.native;
    paintSettings(s);
    patchList(list, data.shares, (x) => String(x.id), row, (node, x) => paintRow(node, x));
    empty.classList.toggle("hidden", data.shares.length > 0);
  }
  refreshShared = refresh;
  void refresh();
  const timer = window.setInterval(() => void refresh(), 15000);
  return () => { alive = false; refreshShared = null; window.clearInterval(timer); };
}

let registered = false;

export function registerSharing(): void {
  if (registered) return;
  registered = true;
  void api<ShareSettings>("/sharing/settings").then((s) => { native = s.native; }).catch(() => undefined);
  selectbarExtras.push({ label: "Share", icon: "share", handler: (ids) => {
    if (!ids.length) return;
    const bar = document.querySelector<HTMLElement>(".sel-bar");
    const rect = bar?.getBoundingClientRect();
    openContextMenu(rect ? rect.left + 160 : 200, rect ? rect.top - 160 : 200, shareEntries(ids));
  } });
  tileHooks.ctx.push((item) => {
    const ids = state.selection.has(item.id) && state.selection.size > 1 ? [...state.selection] : [item.id];
    return [{ label: "Share Link...", icon: "link", action: () => void shareLinkFlow(ids) },
      { label: "Web Gallery...", icon: "browser", action: () => void galleryFlow(ids) }];
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
