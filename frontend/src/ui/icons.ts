import { GLYPHS, svg } from "../theme/icons.js";
import { EXTRA_GLYPHS, type ExtraIcon, extraSvg } from "./icons-extra.js";

export type IconName = keyof typeof GLYPHS | ExtraIcon;

export function iconEl(name: IconName, extraClass = ""): HTMLSpanElement {
  const span = document.createElement("span");
  span.className = extraClass ? `icon ${extraClass}` : "icon";
  span.innerHTML = name in EXTRA_GLYPHS ? extraSvg(name as ExtraIcon) : svg(name, { cssSized: true });
  return span;
}

export function iconInto(target: HTMLElement, name: IconName): void {
  target.replaceChildren(iconEl(name));
}
