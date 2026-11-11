import { afterEach, describe, expect, it, vi } from "vitest";

const media = (id: number, name: string) => ({ id, name, size: 1000, width: 400, height: 300 });
const set = { id: 1, match_kind: "visual", similarity: 96, keeper: media(4, "keeper.jpg"), members: [media(1, "copy.jpg")] };
const refusal = { detail: "The copy to keep is in the Trash or not in this set; choose another copy to keep" };

vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
  if (url === "/api/dedup/sets") return { ok: true, status: 200, json: async () => ({ sets: [set] }) };
  if (init?.method === "POST") return { ok: false, status: 409, statusText: "Conflict", json: async () => refusal };
  return { ok: true, status: 200, json: async () => ({}) };
}));
vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} });

import { mountDedupPage } from "../src/ui/components/dedup.js";

type Listener = (reason: unknown) => void;
const node = (globalThis as unknown as { process: { on(e: string, f: Listener): void; off(e: string, f: Listener): void } }).process;
const unhandled: unknown[] = [];
const onUnhandled = (reason: unknown) => unhandled.push(reason);

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 0));
}

function errorToasts(): string[] {
  return [...document.querySelectorAll(".toast-error")].map((n) => n.textContent ?? "");
}

describe("duplicates page", () => {
  afterEach(() => {
    node.off("unhandledRejection", onUnhandled);
    unhandled.length = 0;
  });

  it.each([
    ["Keep best, trash the rest"],
    ["Keep this one"],
    ["Trash"],
    ["Resolve all exact"],
  ])("shows a refused %s as an error toast", async (label) => {
    node.on("unhandledRejection", onUnhandled);
    const before = errorToasts().length;
    const host = document.createElement("div");
    document.body.append(host);
    const off = mountDedupPage(host);
    await settle();
    const button = [...host.querySelectorAll("button")].find((b) => b.textContent === label) as HTMLButtonElement;
    expect(button).toBeTruthy();
    button.disabled = false;
    button.click();
    await settle();
    off();
    host.remove();
    expect(unhandled).toEqual([]);
    expect(errorToasts().slice(before).some((t) => t.includes("choose another copy to keep"))).toBe(true);
  });
});
