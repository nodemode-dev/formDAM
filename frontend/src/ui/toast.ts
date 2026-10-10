import { h } from "./dom.js";

let host: HTMLElement | null = null;

function ensureHost(): HTMLElement {
  if (!host) {
    host = h("div", { class: "toast-host" });
    document.body.append(host);
  }
  return host;
}

export function toast(message: string, tone: "info" | "error" = "info"): void {
  const node = h("div", { class: `toast toast-${tone} pop-surface` }, message);
  ensureHost().append(node);
  requestAnimationFrame(() => node.classList.add("toast-in"));
  setTimeout(() => {
    node.classList.remove("toast-in");
    setTimeout(() => node.remove(), 260);
  }, 3400);
}
