import { prefGet, prefSet } from "./prefstore.js";

export interface GlassPrefs {
  strength: number;
  blur: number;
  frost: number;
  tint: number;
  gradient: number;
  opacity: number;
  ver?: number;
}

export interface ThemePrefs {
  accent: string;
  glass: GlassPrefs;
  background: boolean;
  vibrancy: boolean;
  vibTint: number;
  winBlur: number;
  winFrost: number;
  fade: number;
  side: { opacity: number; blur: number };
  top: { opacity: number; blur: number };
  tileRadius: number;
  bg: { radius: number; glow: number; bloom: number };
}

export const ACCENT_SWATCHES = ["#f0a84b", "#f15a29", "#7ee262", "#4dd7f2", "#a78bfa", "#f26d9a"];

export const DEFAULT_THEME: ThemePrefs = {
  accent: "#f0a84b",
  glass: { strength: 1, blur: 36, frost: 1.9, tint: 0.12, gradient: 1, opacity: 0.38, ver: 2 },
  background: true,
  vibrancy: true,
  vibTint: 46,
  winBlur: 28,
  winFrost: 0,
  fade: 0,
  side: { opacity: 58, blur: 28 },
  top: { opacity: 16, blur: 22 },
  tileRadius: 10,
  bg: { radius: 320, glow: 66, bloom: 60 },
};

const KEY = "theme";

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const value = parseInt(clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean, 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function lighten(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  const up = (c: number) => Math.round(c + (255 - c) * amount);
  return `#${[up(r), up(g), up(b)].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

function migrateBg(raw: Partial<{ radius: number; glow: number; bloom: number }> | undefined): ThemePrefs["bg"] {
  if (!raw) return { ...DEFAULT_THEME.bg };
  if (raw.glow === undefined && raw.bloom !== undefined) {
    const old = Math.min(100, Math.max(0, raw.bloom));
    return {
      radius: raw.radius ?? DEFAULT_THEME.bg.radius,
      glow: Math.round(25 + 0.75 * old),
      bloom: Math.round(9 + 0.92 * old),
    };
  }
  return { ...DEFAULT_THEME.bg, ...raw };
}

export function loadTheme(): ThemePrefs {
  const parsed = prefGet<(Partial<ThemePrefs> & { winFade?: number }) | null>(KEY, null);
  if (!parsed) return { ...DEFAULT_THEME, glass: { ...DEFAULT_THEME.glass }, bg: { ...DEFAULT_THEME.bg } };
  // Migration: the retired winFade was macOS window opacity (100 = off); fade is
  // its background-only inverse.
  const legacy = parsed.winFade !== undefined && parsed.winFade < 100
    ? 100 - Math.max(30, Math.min(100, parsed.winFade))
    : 0;
  return {
    accent: parsed.accent ?? DEFAULT_THEME.accent,
    glass: { ...DEFAULT_THEME.glass, ...(parsed.glass?.ver === DEFAULT_THEME.glass.ver ? parsed.glass : {}) },
    background: parsed.background ?? DEFAULT_THEME.background,
    vibrancy: true,
    vibTint: Math.max(-100, Math.min(100, parsed.vibTint ?? DEFAULT_THEME.vibTint)),
    winBlur: parsed.winBlur ? parsed.winBlur : DEFAULT_THEME.winBlur,
    winFrost: parsed.winFrost ?? DEFAULT_THEME.winFrost,
    fade: Math.max(0, Math.min(100, parsed.fade ?? legacy)),
    side: {
      opacity: Math.max(0, Math.min(100, parsed.side?.opacity ?? DEFAULT_THEME.side.opacity)),
      blur: Math.max(0, Math.min(64, parsed.side?.blur ?? DEFAULT_THEME.side.blur)),
    },
    top: {
      opacity: Math.max(0, Math.min(100, parsed.top?.opacity ?? DEFAULT_THEME.top.opacity)),
      blur: Math.max(0, Math.min(64, parsed.top?.blur ?? DEFAULT_THEME.top.blur)),
    },
    tileRadius: parsed.tileRadius ?? DEFAULT_THEME.tileRadius,
    bg: migrateBg(parsed.bg),
  };
}

export function saveTheme(prefs: ThemePrefs): void {
  prefSet(KEY, prefs);
}

export function applyTheme(prefs: ThemePrefs): void {
  const root = document.documentElement.style;
  const [r, g, b] = hexToRgb(prefs.accent);
  root.setProperty("--accent", prefs.accent);
  root.setProperty("--accent-2", lighten(prefs.accent, 0.35));
  root.setProperty("--accent-glow", `rgba(${r}, ${g}, ${b}, 0.45)`);
  root.setProperty("--accent-soft", `rgba(${r}, ${g}, ${b}, 0.14)`);

  const glass = prefs.glass;
  const blur = Math.round(glass.blur * glass.strength);
  const alpha = Math.min(0.6, Math.max(0.03, glass.opacity * glass.strength));
  const tintAlpha = Math.min(0.4, glass.tint);
  root.setProperty("--glass-blur", `${blur}px`);
  root.setProperty("--glass-saturate", `${Math.round(glass.frost * 100)}%`);
  root.setProperty("--glass-brightness", `${(0.9 + glass.frost * 0.095).toFixed(2)}`);
  root.setProperty("--glass-bg", `rgba(${18 + r * tintAlpha * 0.3}, ${16 + g * tintAlpha * 0.3}, ${14 + b * tintAlpha * 0.3}, ${alpha.toFixed(3)})`);
  const sideAlpha = Math.min(0.98, Math.max(0, prefs.side.opacity) / 100);
  root.setProperty("--glass-bg-side", `rgba(${18 + r * tintAlpha * 0.3}, ${16 + g * tintAlpha * 0.3}, ${14 + b * tintAlpha * 0.3}, ${sideAlpha.toFixed(3)})`);
  root.setProperty("--glass-blur-side", `${Math.max(0, Math.min(64, prefs.side.blur))}px`);
  const topAlpha = Math.min(0.98, Math.max(0, prefs.top.opacity) / 100);
  root.setProperty("--glass-bg-top", `rgba(${18 + r * tintAlpha * 0.3}, ${16 + g * tintAlpha * 0.3}, ${14 + b * tintAlpha * 0.3}, ${topAlpha.toFixed(3)})`);
  root.setProperty("--glass-blur-top", `${Math.max(0, Math.min(64, prefs.top.blur))}px`);
  root.setProperty("--glass-sheen", `rgba(255, 255, 255, ${(0.075 * glass.gradient).toFixed(3)})`);
  root.setProperty("--glass-rim-top", `rgba(255, 255, 255, ${(0.32 * glass.gradient).toFixed(3)})`);
  root.setProperty("--glass-rim-mid", `rgba(255, 255, 255, ${(0.07 * glass.gradient).toFixed(3)})`);
  root.setProperty("--glass-rim-bottom", `rgba(255, 255, 255, ${(0.02 * glass.gradient).toFixed(3)})`);
  document.documentElement.classList.toggle("vibrancy", prefs.vibrancy);
  // Window fade, background-only: the webview backdrop is transparent (shell
  // clears it), so the app background is THIS paint & its alpha is 1 - fade.
  // Photos, text, icons & panels never carry the alpha, so they stay solid at
  // every setting. Tint picks the paint colour, frost lifts it toward white.
  const t = Math.max(-100, Math.min(100, prefs.vibTint)) / 100;
  const theme = [10, 6, 3];
  const light = [245, 242, 236];
  const base = theme.map((c, i) =>
    t >= 0 ? Math.round(c * (1 - t)) : Math.round(c + (light[i] - c) * -t),
  );
  const f = Math.max(0, Math.min(100, prefs.winFrost)) / 100;
  const rgb = base.map((c) => Math.round(c + (255 - c) * f * 0.9));
  const fadeAlpha = 1 - Math.max(0, Math.min(100, prefs.fade)) / 100;
  const shade = (mult: number) =>
    `rgba(${rgb.map((c) => Math.min(255, Math.round(c * mult))).join(", ")}, ${fadeAlpha.toFixed(3)})`;
  const rootStyle = document.documentElement.style;
  rootStyle.setProperty("--vib-body", shade(1));

  let vibStyle = document.getElementById("dam-vib") as HTMLStyleElement | null;
  if (!vibStyle) {
    vibStyle = document.createElement("style");
    vibStyle.id = "dam-vib";
    document.head.appendChild(vibStyle);
  }
  vibStyle.textContent = `html.vibrancy { background: transparent !important; }
     html.vibrancy body { background: transparent !important; }
     html.vibrancy #app { background: ${shade(1)} !important; }`;
  document.documentElement.style.setProperty("--tile-radius", `${prefs.tileRadius}px`);
  window.dispatchEvent(new Event("resize"));
}
