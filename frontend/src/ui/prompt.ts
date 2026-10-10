import { h } from "./dom.js";
import { openModal } from "./modal.js";

export function promptText(title: string, initial = "", hint = "", confirmLabel = "OK"): Promise<string | null> {
  return new Promise((resolve) => {
    const modal = openModal(title, 380);
    const input = h("input", { class: "field-input", spellcheck: "false", autocomplete: "off" }) as HTMLInputElement;
    input.value = initial;
    let settled = false;
    const finish = (value: string | null) => {
      if (settled) return;
      settled = true;
      modal.close();
      resolve(value);
    };
    const ok = h("button", { class: "btn primary", type: "button" }, confirmLabel);
    const cancel = h("button", { class: "btn", type: "button" }, "Cancel");
    ok.addEventListener("click", () => finish(input.value));
    cancel.addEventListener("click", () => finish(null));
    input.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Enter") finish(input.value);
      if (event.key === "Escape") finish(null);
    });
    modal.root.addEventListener("click", (event) => {
      if (event.target === modal.root) finish(null);
    });
    modal.body.append(
      ...(hint ? [h("div", { class: "field-label" }, hint)] : []),
      input,
      h("div", { class: "modal-foot" }, h("span", { class: "head-spacer" }), cancel, ok),
    );
    requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
  });
}
