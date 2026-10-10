const KEY_RE = /(?:^#|&)dam-key=([0-9a-f]{64})/;

export async function openSession(): Promise<boolean> {
  const match = location.hash.match(KEY_RE);
  if (match) {
    history.replaceState(null, "", location.pathname + location.search);
    try {
      const res = await fetch("/api/session", { method: "POST", headers: { "x-dam-local": "1", "x-dam-shell": match[1] } });
      if (res.ok) return true;
    } catch {
      return false;
    }
  }
  try {
    const res = await fetch("/api/session");
    return res.ok && ((await res.json()) as { window: boolean }).window;
  } catch {
    return false;
  }
}

export function showLockout(root: HTMLElement): void {
  const card = document.createElement("div");
  card.className = "lockout-card";
  const title = document.createElement("h1");
  title.textContent = "This window is not connected to DAM";
  const body = document.createElement("p");
  body.textContent = "DAM only answers windows it opened itself, so other programs on this computer cannot use your library. "
    + "Open DAM from its app, or run ./DAM (DAM.bat on Windows) and use the window it opens or the address it prints.";
  card.append(title, body);
  root.replaceChildren(card);
  window.addEventListener("hashchange", () => {
    if (KEY_RE.test(location.hash)) void openSession().then((ok) => { if (ok) location.reload(); });
  });
}
