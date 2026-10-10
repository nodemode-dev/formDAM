import { h } from "./dom.js";
import { iconEl, type IconName } from "./icons.js";

export interface CtxItem {
  label: string;
  icon?: IconName;
  danger?: boolean;
  selected?: boolean;
  action: () => void;
}

export type CtxEntry = CtxItem | "sep";

let current: HTMLElement | null = null;

export function closeContextMenu(): void {
  current?.remove();
  current = null;
}

export function openContextMenu(x: number, y: number, entries: CtxEntry[]): void {
  closeContextMenu();
  const menu = h("div", { class: "ctx-menu pop-surface" });
  for (const entry of entries) {
    if (entry === "sep") {
      menu.append(h("div", { class: "ctx-sep" }));
      continue;
    }
    const item = h("button", { class: `ctx-item${entry.danger ? " danger" : ""}${entry.selected ? " selected" : ""}`, type: "button" },
      entry.icon ? iconEl(entry.icon) : h("span", { style: "width:15px" }),
      entry.label);
    item.addEventListener("click", () => {
      closeContextMenu();
      entry.action();
    });
    menu.append(item);
  }
  document.body.append(menu);
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.min(x, window.innerWidth - rect.width - 8)}px`;
  menu.style.top = `${Math.min(y, window.innerHeight - rect.height - 8)}px`;
  current = menu;

  const dismiss = (event: Event) => {
    if (event instanceof KeyboardEvent && event.key !== "Escape") return;
    if (event instanceof PointerEvent && menu.contains(event.target as Node)) return;
    closeContextMenu();
    window.removeEventListener("pointerdown", dismiss, true);
    window.removeEventListener("keydown", dismiss, true);
    window.removeEventListener("blur", dismiss);
  };
  window.addEventListener("pointerdown", dismiss, true);
  window.addEventListener("keydown", dismiss, true);
  window.addEventListener("blur", dismiss);
}
