import { api } from "../../engine/api.js";
import { countFmt } from "../../engine/format.js";
import { keywordState, loadKeywords, navigate, type QueryRule, type QuerySpec } from "../../engine/store.js";
import { h } from "../dom.js";
import { setText } from "../keyed.js";
import { openModal } from "../modal.js";
import { ruleEditor, smartFromSpec, specHash } from "./organize.js";

export function advancedFindFlow(initial: QueryRule[] = [{ field: "flag", value: "photo" }]): void {
  const modal = openModal("Advanced Find", 680);
  const rules: QueryRule[] = initial.map((r) => ({ ...r }));
  const match = h("select", { class: "field-input" }, h("option", { value: "all" }, "all"), h("option", { value: "any" }, "any")) as HTMLSelectElement;
  const count = h("span", { class: "rule-count" }, "");
  let timer = 0;
  let seq = 0;
  const spec = (): QuerySpec => ({ rules, match: match.value as "all" | "any", expand_stacks: true });
  const recount = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const mine = ++seq;
      const res = await api<{ count: number }>(`/browse/count?spec=${encodeURIComponent(JSON.stringify(spec()))}`);
      if (mine === seq) setText(count, `${countFmt(res.count)} matching item${res.count === 1 ? "" : "s"}`);
    }, 220);
  };
  match.addEventListener("change", recount);
  const save = h("button", { class: "btn", type: "button" }, "Save as Smart Album");
  save.addEventListener("click", () => {
    modal.close();
    void smartFromSpec("Find Results", spec());
  });
  const show = h("button", { class: "btn primary", type: "button" }, "Show Results");
  show.addEventListener("click", () => {
    modal.close();
    navigate(specHash({ ...spec(), title: "Find Results" } as QuerySpec));
  });
  void (keywordState.loaded ? Promise.resolve() : loadKeywords()).then(() => {
    modal.body.append(
      h("div", { class: "row-gap" }, h("span", {}, "Find items matching"), match, h("span", {}, "of these rules")),
      ruleEditor(rules, recount),
      h("div", { class: "modal-foot" }, count, h("span", { class: "head-spacer" }), save, show),
    );
    recount();
  });
}

let bound = false;

export function registerFind(): void {
  if (bound) return;
  bound = true;
  window.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey) || event.shiftKey || event.key.toLowerCase() !== "f") return;
    if (document.querySelector(".modal-backdrop")) return;
    event.preventDefault();
    advancedFindFlow();
  });
}
