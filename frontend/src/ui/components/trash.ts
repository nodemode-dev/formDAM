import { clearVaultToken, api, hasVaultToken, setVaultToken, thumbUrl } from "../../engine/api.js";
import { countFmt, humanBytes } from "../../engine/format.js";
import { invalidateMedia, loadTrash, on, refreshSummary, state } from "../../engine/store.js";
import { h } from "../dom.js";
import { iconEl } from "../icons.js";
import { openModal, textField } from "../modal.js";
import { toast } from "../toast.js";

export async function vaultGate(): Promise<boolean> {
  // Within one visit an obtained token stands; every visit starts w/o one
  // (the vault pages clear it on unmount), so each entry re-locks.
  if (hasVaultToken()) return true;
  const status = await api<{ configured: boolean }>("/vault/status");
  if (status.configured) {
    try {
      const kc = await api<{ available: boolean; stored: boolean }>("/vault/keychain/status");
      if (kc.available && kc.stored) {
        const res = await api<{ token: string }>("/vault/bio/unlock", { method: "POST" });
        setVaultToken(res.token);
        return true;
      }
    } catch {
      /* device unlock unavailable, cancelled, or mismatched: fall through to the passkey modal */
    }
  }
  const device = await Promise.all([
    api<{ available: boolean; stored: boolean }>("/vault/keychain/status"),
    api<{ method: string; store: string }>("/vault/device"),
  ]).then(([kc, labels]) => ({ ...kc, ...labels })).catch(() => null);
  return new Promise((resolve) => {
    const modal = openModal(status.configured ? "Unlock Recently Deleted" : "Set a vault passkey");
    const hint = status.configured
      ? "Hidden, Recently Deleted & private albums w/o their own passkey are encrypted on disk w/ the vault passkey."
      : "Pick a passkey. It encrypts Hidden, Recently Deleted & any private album that does not set its own. If you forget it, those items cannot be recovered, so save it below when offered.";
    const { wrap, input } = textField("Passkey", "password", "At least 4 characters");
    const kcCheck = h("input", { type: "checkbox" }) as HTMLInputElement;
    kcCheck.checked = Boolean(device?.stored);
    const kcRow = device?.available
      ? h("label", { class: "field-check" }, kcCheck, `Save to ${device.store} so ${device.method} can unlock this next time`)
      : null;
    const go = h("button", { class: "btn primary", type: "button" }, iconEl("lock"), status.configured ? "Unlock" : "Set & Unlock");
    let settled = false;
    const done = (ok: boolean) => {
      if (!settled) {
        settled = true;
        resolve(ok);
      }
    };
    go.addEventListener("click", async () => {
      try {
        const path = status.configured ? "/vault/unlock" : "/vault/setup";
        const res = await api<{ token: string }>(path, { method: "POST", body: JSON.stringify({ passkey: input.value }) });
        setVaultToken(res.token);
        if (kcRow && kcCheck.checked) {
          try {
            await api("/vault/keychain/enable", { method: "POST", body: JSON.stringify({ passkey: input.value }) });
            toast(`Saved to ${device?.store}; ${device?.method} will unlock next time`);
          } catch (err) {
            toast(String((err as Error).message), "error");
          }
        }
        modal.close();
        done(true);
      } catch (err) {
        toast(String((err as Error).message), "error");
      }
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") go.click();
    });
    modal.root.addEventListener("transitionend", () => {
      if (!document.body.contains(modal.root)) done(false);
    });
    modal.body.append(h("p", { style: "margin:0;color:var(--text-muted);font-size:13px" }, hint), wrap, ...(kcRow ? [kcRow] : []), h("div", { class: "modal-actions" }, go));
    input.focus();
  });
}

export function mountTrashPage(host: HTMLElement): () => void {
  const rows = h("div", { class: "list-rows" });
  const emptyBtn = h("button", { class: "btn danger", type: "button" }, iconEl("trash"), "Empty Trash");
  const note = h("p", { style: "margin:0 0 12px;color:var(--text-faint);font-size:12.5px" }, "");
  const pad = h(
    "div",
    { class: "view-pad" },
    h("div", { class: "section-head" }, h("h2", {}, "Recently Deleted"), h("span", { class: "head-spacer" }), emptyBtn),
    note,
    rows,
  );
  host.append(pad);

  function render(): void {
    note.textContent = `Items are permanently removed after ${state.trashRetention} days. Duplicate resolutions land here too, so they are always reversible.`;
    if (state.trash.length === 0) {
      rows.replaceChildren(
        h("div", { class: "empty-center" }, h("div", { class: "empty-card glass-panel" },
          iconEl("trash"),
          h("span", { class: "empty-title" }, "Nothing in the trash"),
          h("span", { class: "empty-sub" }, "Deleted items wait here before permanent removal."),
        )),
      );
      return;
    }
    rows.replaceChildren(
      ...state.trash.map((item) => {
        const img = h("img", { alt: "", loading: "lazy", src: thumbUrl(item.id, 192) });
        const restoreBtn = h("button", { class: "btn", type: "button" }, "Restore");
        const killBtn = h("button", { class: "icon-btn danger", type: "button", "aria-label": "Delete forever" }, iconEl("close"));
        restoreBtn.addEventListener("click", async () => {
          await api(`/trash/${item.id}/restore`, { method: "POST" });
          invalidateMedia();
          void loadTrash();
          void refreshSummary();
          toast("Restored to Library");
        });
        killBtn.addEventListener("click", async () => {
          await api(`/trash/${item.id}`, { method: "DELETE" });
          void loadTrash();
          void refreshSummary();
          toast("Deleted forever");
        });
        const reason = item.trash_reason?.startsWith("duplicate:") ? " · removed as duplicate" : "";
        return h(
          "div",
          { class: "list-row glass-panel" },
          h("div", { class: "list-thumb" }, img),
          h("div", { class: "list-main" },
            h("div", { class: "list-title" }, item.name),
            h("div", { class: "list-sub" }, `${humanBytes(item.size)} · ${countFmt(item.days_left ?? 0)} days left${reason}`),
          ),
          restoreBtn,
          killBtn,
        );
      }),
    );
  }

  emptyBtn.addEventListener("click", async () => {
    const res = await api<{ deleted: number }>("/trash/empty", { method: "POST" });
    void loadTrash();
    void refreshSummary();
    toast(`Deleted ${countFmt(res.deleted)} items forever`);
  });

  const off = on("trash", render);
  // Privacy gate: nothing renders until THIS visit unlocks. Cached items from
  // a previous unlocked visit are discarded so they can never paint early.
  state.trash = [];
  rows.replaceChildren(
    h("div", { class: "empty-center" }, h("div", { class: "empty-card glass-panel" },
      iconEl("trash"),
      h("span", { class: "empty-title" }, "Locked"),
      h("span", { class: "empty-sub" }, "Your vault passkey, or device unlock where it is set up, is required to view Recently Deleted."),
    )),
  );
  let gone = false;
  void (async () => {
    const ok = await vaultGate();
    if (gone) return;
    if (!ok) {
      history.back();
      return;
    }
    try {
      await loadTrash();
    } catch {
      /* fetch failure renders the empty state below */
    }
    if (!gone) render();
  })();
  return () => {
    gone = true;
    clearVaultToken();
    state.trash = [];
    off();
    clearVaultToken();
  };
}
