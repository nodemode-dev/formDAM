import { on, setZoom, state } from "../engine/store.js";
import { h } from "./dom.js";
import { iconEl } from "./icons.js";

export function zoomControl(): HTMLElement {
  const slider = h("input", { type: "range", min: "96", max: "512", step: "8", value: String(state.zoom) }) as HTMLInputElement;
  slider.addEventListener("input", () => setZoom(Number(slider.value)));
  on("zoom", () => {
    slider.value = String(state.zoom);
  });
  const minus = h("button", { class: "icon-btn", type: "button", "aria-label": "Smaller tiles" }, iconEl("minus"));
  minus.addEventListener("click", () => setZoom(state.zoom - 24));
  const plus = h("button", { class: "icon-btn", type: "button", "aria-label": "Larger tiles" }, iconEl("plus"));
  plus.addEventListener("click", () => setZoom(state.zoom + 24));
  return h("span", { class: "zoom-wrap" }, minus, slider, plus);
}

export function bindTileSize(grid: HTMLElement): () => void {
  const apply = () => grid.style.setProperty("--tile", `${state.zoom}px`);
  apply();
  return on("zoom", apply);
}
