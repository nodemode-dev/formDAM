import { api, apiUpload } from "../../engine/api.js";
import { countFmt, fullStamp } from "../../engine/format.js";
import { invalidateMedia, loadAlbums, navigate, refreshSummary, state } from "../../engine/store.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { patchList, setText } from "../keyed.js";
import { openModal, textField } from "../modal.js";
import { toast } from "../toast.js";
import { pickFolder } from "./outputs.js";

interface Job { phase: string; error?: string; counts: Record<string, number>; path?: string; album_id?: number | null; stack_id?: number | null }
interface PackageRow { id: number; direction: "in" | "out"; kind: string; title: string; count: number; sender: string | null; path: string | null; created_ts: number; exists: boolean; album_id: number | null }
interface Note { id: string; author: string; text: string; ts: number; mine: number }

const MIN_PASSWORD = 16;
let native = false;

function waitJob(id: string): Promise<Job> {
  return new Promise((resolve) => {
    const tick = async () => {
      const job = await api<Job>(`/jobs/${id}`);
      if (job.phase === "running") window.setTimeout(() => void tick(), 600);
      else resolve(job);
    };
    void tick();
  });
}

function check(label: string, on: boolean): { wrap: HTMLElement; input: HTMLInputElement } {
  const input = h("input", { type: "checkbox" }) as HTMLInputElement;
  input.checked = on;
  return { wrap: h("label", { class: "field-check" }, input, label), input };
}

function seg(options: Array<[string, string]>, value: string): { el: HTMLElement; get: () => string } {
  let current = value;
  const el = h("div", { class: "seg" });
  for (const [key, label] of options) {
    const btn = h("button", { type: "button", class: key === value ? "active" : "" }, label);
    btn.addEventListener("click", () => {
      current = key;
      el.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
    });
    el.append(btn);
  }
  return { el, get: () => current };
}

function sentPanel(job: Job, password: string, packageId: number | null): HTMLElement {
  const copy = h("button", { class: "btn", type: "button" }, iconEl("copy"), "Copy Password");
  copy.addEventListener("click", () => void navigator.clipboard?.writeText(password).then(() => toast("Password copied")));
  const actions = h("div", { class: "row-gap" }, copy);
  const send = (service: string, label: string) => {
    const btn = h("button", { class: "btn", type: "button" }, label);
    btn.addEventListener("click", () => {
      if (packageId === null) return;
      void api("/packages/send", { method: "POST", body: JSON.stringify({ package: packageId, service }) }).catch((err) => toast((err as Error).message, "error"));
    });
    return btn;
  };
  actions.append(send("reveal", "Show in Finder"));
  if (native) actions.append(send("airdrop", "AirDrop"), send("mail", "Mail"), send("messages", "Messages"));
  const c = job.counts;
  const facts = [`${countFmt(c.items ?? 0)} item${(c.items ?? 0) === 1 ? "" : "s"} encrypted with AES-256`];
  if (c.skipped) facts.push(`${countFmt(c.skipped)} private, hidden or deleted left out`);
  if (c.converted) facts.push(`${countFmt(c.converted)} sent as JPEG because their location could not be removed in place`);
  return h("div", { class: "share-result" },
    h("p", { class: "field-hint" }, facts.join(" · ")),
    h("div", { class: "pkg-path" }, job.path ?? ""),
    h("p", { class: "field-hint" }, "Send the file any way you like. Give the password separately, by phone or another app, never in the same message as the file."),
    h("div", { class: "pkg-password" }, password),
    actions);
}

export async function packageFlow(ids: number[], album?: { id: number; name: string }): Promise<void> {
  const [suggested, list] = await Promise.all([
    api<{ password: string }>("/packages/password", { method: "POST" }),
    api<{ native: boolean }>("/packages"),
  ]);
  native = list.native;
  const modal = openModal(album ? "Share Album as Encrypted Package" : "Share as Encrypted Package", 480);
  const first = ids.length === 1 ? state.byId.get(ids[0]) : undefined;
  const title = textField("Title", "text", "Shared Photos");
  title.input.value = album?.name ?? first?.title ?? "Shared Photos";
  const addAs = seg([["album", "Album"], ["stack", "Stack"]], "album");
  const password = textField("Password", "text", "At least 16 characters");
  password.input.value = suggested.password;
  const regen = h("button", { class: "btn", type: "button" }, "New Password");
  regen.addEventListener("click", async () => { password.input.value = (await api<{ password: string }>("/packages/password", { method: "POST" })).password; });
  const location = check("Include location", false);
  const dest = textField("Save to", "text", "~/Desktop");
  dest.input.value = "~/Desktop";
  const choose = h("button", { class: "btn", type: "button" }, "Choose...");
  choose.addEventListener("click", async () => { const p = await pickFolder("Save the package in"); if (p) dest.input.value = p; });
  const error = h("p", { class: "field-error" }, "");
  const create = h("button", { class: "btn primary", type: "button" }, "Create Package");
  const form = h("div", { class: "share-form" },
    h("p", { class: "field-hint" }, album
      ? "Everything in the album, its notes and its share id go into one AES-256 encrypted zip. When the other person opens it in DAM, it becomes the same shared album; packages either of you send later add to it."
      : "The originals, their edits and metadata go into one AES-256 encrypted zip with scrambled file names. The other person drops it into DAM and enters the password. Zip encryption guesses passwords quickly offline, so keep the generated one unless yours is long and random, and send it by a different route than the zip."),
    title.wrap,
    album ? h("span", { class: "hidden" }) : h("label", { class: "field" }, h("span", { class: "field-label" }, "Arrives as"), addAs.el),
    h("div", { class: "row-gap pkg-pw-row" }, password.wrap, regen),
    location.wrap, h("div", { class: "row-gap pkg-pw-row" }, dest.wrap, choose), error,
    h("div", { class: "row-gap" }, create));
  create.addEventListener("click", async () => {
    if (password.input.value.length < MIN_PASSWORD) {
      setText(error, `Use at least ${MIN_PASSWORD} characters`);
      return;
    }
    setText(error, "");
    create.setAttribute("disabled", "true");
    setText(create, "Encrypting...");
    try {
      const res = await api<{ job_id: string }>("/packages", { method: "POST", body: JSON.stringify({
        ids, album_id: album?.id ?? null, title: title.input.value.trim(), password: password.input.value,
        dest: dest.input.value.trim() || "~/Desktop", include_location: location.input.checked, add_as: addAs.get(),
      }) });
      const job = await waitJob(res.job_id);
      if (job.phase !== "done") throw new Error(job.error || "The package could not be made");
      const rows = await api<{ packages: PackageRow[] }>("/packages");
      const made = rows.packages.find((p) => p.direction === "out" && p.path === job.path);
      modal.body.replaceChildren(sentPanel(job, password.input.value, made?.id ?? null));
      void refreshPackages?.();
    } catch (err) {
      create.removeAttribute("disabled");
      setText(create, "Create Package");
      setText(error, (err as { detail?: string }).detail ?? (err as Error).message);
    }
  });
  modal.body.append(form);
}

export async function openPackageFlow(file: File): Promise<boolean> {
  const form = new FormData();
  form.append("file", file, file.name);
  const info = await apiUpload<{ package: boolean; token?: string; files?: number }>("/packages/inspect", form);
  if (!info.package || !info.token) return false;
  const token = info.token;
  const modal = openModal("Open Shared Package", 440);
  const password = textField("Password", "password", "The password you were given");
  const addAs = seg([["album", "New Album"], ["stack", "Stack"]], "album");
  const error = h("p", { class: "field-error" }, "");
  const open = h("button", { class: "btn primary", type: "button" }, "Open");
  const cancel = h("button", { class: "btn", type: "button" }, "Cancel");
  let opened = false;
  cancel.addEventListener("click", () => { modal.close(); });
  const observer = new MutationObserver(() => {
    if (!modal.root.isConnected) {
      observer.disconnect();
      if (!opened) void api(`/packages/incoming/${token}`, { method: "DELETE" }).catch(() => undefined);
    }
  });
  observer.observe(document.body, { childList: true });
  const go = async () => {
    if (!password.input.value) return;
    setText(error, "");
    open.setAttribute("disabled", "true");
    setText(open, "Decrypting...");
    try {
      const res = await api<{ job_id: string; title: string; count: number; album: string | null; sender: string }>("/packages/open",
        { method: "POST", body: JSON.stringify({ token, password: password.input.value, add_as: addAs.get() }) });
      opened = true;
      const job = await waitJob(res.job_id);
      modal.close();
      if (job.phase !== "done") {
        toast(job.error || "The package could not be opened", "error");
        return;
      }
      const c = job.counts;
      toast(`${res.title}: ${countFmt(c.imported ?? 0)} new, ${countFmt(c.already ?? 0)} already here${c.notes ? `, ${c.notes} new note${c.notes === 1 ? "" : "s"}` : ""}${res.sender ? ` from ${res.sender}` : ""}`);
      invalidateMedia();
      void refreshSummary();
      await loadAlbums();
      void refreshPackages?.();
      if (job.album_id) navigate(`#/album/${job.album_id}`);
    } catch (err) {
      open.removeAttribute("disabled");
      setText(open, "Open");
      setText(error, (err as { detail?: string }).detail ?? (err as Error).message);
    }
  };
  open.addEventListener("click", () => void go());
  password.input.addEventListener("keydown", (event) => { event.stopPropagation(); if (event.key === "Enter") void go(); });
  modal.body.append(h("div", { class: "share-form" },
    h("p", { class: "field-hint" }, `${file.name} is an encrypted DAM package with ${countFmt(info.files ?? 0)} file${info.files === 1 ? "" : "s"}. Its names and contents stay scrambled until the password opens it.`),
    password.wrap, h("label", { class: "field" }, h("span", { class: "field-label" }, "Add as (shared albums always join their album)"), addAs.el),
    error, h("div", { class: "row-gap" }, open, cancel)));
  password.input.focus();
  return true;
}

export async function notesFlow(albumId: number, name: string): Promise<void> {
  const modal = openModal(`Notes · ${name}`, 440);
  const list = h("div", { class: "share-activity" });
  const empty = h("p", { class: "field-hint" }, "No notes yet.");
  const box = h("textarea", { class: "field-input", rows: "3", placeholder: "Add a note for everyone who shares this album" }) as HTMLTextAreaElement;
  box.addEventListener("keydown", (event) => event.stopPropagation());
  const add = h("button", { class: "btn", type: "button" }, "Add Note");
  const paint = (notes: Note[]) => {
    patchList(list, notes, (n) => n.id, (n) => h("div", { class: "share-act" }, h("b", {}, n.author), `: ${n.text}`, h("span", { class: "list-sub" }, ` · ${fullStamp(n.ts)}`)));
    empty.classList.toggle("hidden", notes.length > 0);
  };
  const load = async () => paint((await api<{ notes: Note[] }>(`/albums/${albumId}/notes`)).notes);
  add.addEventListener("click", async () => {
    if (!box.value.trim()) return;
    try {
      await api(`/albums/${albumId}/notes`, { method: "POST", body: JSON.stringify({ text: box.value.trim() }) });
      box.value = "";
      await load();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  });
  modal.body.append(h("div", { class: "share-form" }, empty, list, box,
    h("p", { class: "field-hint" }, "Notes travel inside the next package you send of this album."), h("div", { class: "row-gap" }, add)));
  await load();
}

let refreshPackages: (() => Promise<void>) | null = null;

export function mountPackageList(host: HTMLElement): () => void {
  const list = h("div", { class: "list-rows" });
  const empty = h("p", { class: "field-hint" }, "No packages yet. Select photos and choose Share, or open an album and choose Share Album. To open one you received, drop the .zip anywhere in the window.");
  host.append(empty, list);
  let alive = true;
  const row = (p: PackageRow) => {
    const node = h("div", { class: "list-row glass-panel" },
      h("span", { class: "list-thumb share-kind" }, iconEl(p.direction === "out" ? "share" : "upload")),
      h("div", { class: "list-main" }, h("div", { class: "list-title" }, p.title || "Shared Photos"),
        h("div", { class: "list-sub" }, `${p.direction === "out" ? "Sent" : `Opened${p.sender ? ` from ${p.sender}` : ""}`} · ${p.kind === "stack" ? "stack" : "album"} · ${countFmt(p.count)} item${p.count === 1 ? "" : "s"} · ${fullStamp(p.created_ts)}`)));
    if (p.direction === "out" && p.exists) {
      const show = h("button", { class: "btn", type: "button" }, "Show in Finder");
      show.addEventListener("click", () => void api("/packages/send", { method: "POST", body: JSON.stringify({ package: p.id, service: "reveal" }) }));
      node.append(show);
    } else if (p.album_id) {
      const openBtn = h("button", { class: "btn", type: "button" }, "Open Album");
      openBtn.addEventListener("click", () => navigate(`#/album/${p.album_id}`));
      node.append(openBtn);
    }
    return node;
  };
  const refresh = async () => {
    const data = await api<{ packages: PackageRow[]; native: boolean }>("/packages");
    if (!alive) return;
    native = data.native;
    patchList(list, data.packages, (p) => String(p.id), row);
    empty.classList.toggle("hidden", data.packages.length > 0);
  };
  refreshPackages = refresh;
  void refresh();
  return () => { alive = false; refreshPackages = null; };
}
