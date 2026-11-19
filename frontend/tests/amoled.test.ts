import { beforeEach, describe, expect, it, vi } from "vitest";

vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ value: null }) })));

import { DEFAULT_THEME, OLED_MIRROR, applyTheme, loadTheme } from "../src/engine/theme.js";

const html = document.documentElement;

function themed(amoled: boolean) {
  return { ...DEFAULT_THEME, glass: { ...DEFAULT_THEME.glass }, bg: { ...DEFAULT_THEME.bg }, amoled };
}

describe("AMOLED Black setting", () => {
  beforeEach(() => {
    html.removeAttribute("data-oled");
    localStorage.clear();
  });

  it("is off by default", () => {
    expect(loadTheme().amoled).toBe(false);
  });

  it("sets data-oled and the pre-paint mirror, and removes both again", () => {
    applyTheme(themed(true));
    expect(html.hasAttribute("data-oled")).toBe(true);
    expect(localStorage.getItem(OLED_MIRROR)).toBe("1");
    applyTheme(themed(false));
    expect(html.hasAttribute("data-oled")).toBe(false);
    expect(localStorage.getItem(OLED_MIRROR)).toBeNull();
  });

  it("paints the glass tint and the window black only when on", () => {
    applyTheme(themed(false));
    const warm = html.style.getPropertyValue("--glass-bg");
    expect(warm).not.toMatch(/^rgba\(0, 0, 0,/);
    applyTheme(themed(true));
    expect(html.style.getPropertyValue("--glass-bg")).toMatch(/^rgba\(0, 0, 0,/);
    expect(document.getElementById("dam-vib")?.textContent).toContain("rgba(0, 0, 0, 1.000)");
    applyTheme(themed(false));
    expect(html.style.getPropertyValue("--glass-bg")).toBe(warm);
  });
});
