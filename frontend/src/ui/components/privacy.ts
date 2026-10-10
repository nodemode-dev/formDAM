import { api } from "../../engine/api.js";
import { fullStamp } from "../../engine/format.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { setText } from "../keyed.js";
import { toast } from "../toast.js";

interface Automation { enabled: boolean; has_token: boolean; created_ts: number | null; forced: boolean; token?: string }

export function privacyPane(): HTMLElement {
  const check = h("input", { type: "checkbox" }) as HTMLInputElement;
  const status = h("p", { class: "settings-hint" }, "");
  const tokenBox = h("div", { class: "pkg-password hidden" }, "");
  const copy = h("button", { class: "btn hidden", type: "button" }, iconEl("copy"), "Copy Token");
  const rotate = h("button", { class: "btn hidden", type: "button" }, "New Token");
  let shown = "";
  copy.addEventListener("click", () => void navigator.clipboard?.writeText(shown).then(() => toast("Token copied")));
  const paint = (a: Automation) => {
    check.checked = a.enabled;
    if (a.token) shown = a.token;
    setText(tokenBox, shown);
    tokenBox.classList.toggle("hidden", !shown || !a.enabled);
    copy.classList.toggle("hidden", !shown || !a.enabled);
    rotate.classList.toggle("hidden", !a.enabled);
    let line = a.enabled
      ? `On${a.created_ts ? ` since ${fullStamp(a.created_ts)}` : ""}. Tools that send the token in an x-dam-automation header can use every part of DAM's local API.${shown ? " The token is shown once; copy it now." : ""}`
      : "Off. Only this window and the DAM app itself can use the library.";
    if (a.forced) line += " This engine was started with DAM_AUTOMATION=1, which lets any local program in until it is restarted without it.";
    setText(status, line);
  };
  check.addEventListener("change", async () => {
    try {
      const res = await api<Automation>("/system/automation", { method: "PUT", body: JSON.stringify({ enabled: check.checked }) });
      if (!check.checked) shown = "";
      paint(res);
    } catch (err) {
      toast((err as Error).message, "error");
      paint(await api<Automation>("/system/automation"));
    }
  });
  rotate.addEventListener("click", async () => paint(await api<Automation>("/system/automation/rotate", { method: "POST" })));
  void api<Automation>("/system/automation").then(paint).catch(() => undefined);
  return h("div", {},
    h("label", { class: "field-check" }, check, "Automation Access (scripts, AI agents & MCP tools)"),
    h("p", { class: "settings-hint" }, "Off by default. While it is off, DAM's engine answers only this window and the DAM app; any other program on this computer that tries to read or change your library, including AI agents and MCP servers, is refused. Turning it on issues a token you give to the tool you trust; turning it off revokes it. This guards the doorway that tools are meant to use. A program that already runs as you can still read files on your disk, which is why hidden, deleted & private items are also encrypted in the vault."),
    status, tokenBox, h("div", { class: "row-gap" }, copy, rotate),
    h("p", { class: "settings-hint" }, "Other things that reach beyond this computer are also off until you turn them on: Sync This Library and the Shared Library, both on the Sharing page. Encrypted share packages are files you create and send yourself."));
}
