import { GLYPHS, svg } from "../theme/icons.js";

export type IconName = keyof typeof GLYPHS;

export function iconEl(name: IconName, extraClass = ""): HTMLSpanElement {
  const span = document.createElement("span");
  span.className = extraClass ? `icon ${extraClass}` : "icon";
  span.innerHTML = svg(name, { cssSized: true });
  return span;
}

export function iconInto(target: HTMLElement, name: IconName): void {
  target.replaceChildren(iconEl(name));
}
