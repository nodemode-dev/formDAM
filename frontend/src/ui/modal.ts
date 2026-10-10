import { h } from "./dom.js";
import { iconEl } from "./icons.js";

export interface ModalHandle {
  root: HTMLElement;
  body: HTMLElement;
  close: () => void;
}

export function openModal(title: string, width = 420): ModalHandle {
  const body = h("div", { class: "modal-body" });
  const closeBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Close" }, iconEl("close"));
  const panel = h(
    "div",
    { class: "modal pop-surface", style: `width:${width}px` },
    h("div", { class: "modal-head" }, h("h2", { class: "modal-title" }, title), closeBtn),
    body,
  );
  const root = h("div", { class: "modal-backdrop" }, panel);
  const close = () => {
    root.classList.remove("modal-open");
    setTimeout(() => root.remove(), 180);
  };
  closeBtn.addEventListener("click", close);
  root.addEventListener("click", (event) => {
    if (event.target === root) close();
  });
  document.body.append(root);
  requestAnimationFrame(() => root.classList.add("modal-open"));
  return { root, body, close };
}

export function textField(labelText: string, type = "text", placeholder = ""): { wrap: HTMLElement; input: HTMLInputElement } {
  const input = h("input", { class: "field-input", spellcheck: "false", autocomplete: "off", autocorrect: "off", autocapitalize: "off", type, placeholder }) as HTMLInputElement;
  const wrap = h("label", { class: "field" }, h("span", { class: "field-label" }, labelText), input);
  return { wrap, input };
}
