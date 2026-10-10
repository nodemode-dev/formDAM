import { api } from "../../engine/api.js";
import { prefGet, prefSet } from "../../engine/prefstore.js";
import { setPreloadHud } from "./grid.js";
import {
  ACCENT_SWATCHES, DEFAULT_THEME, applyTheme, loadTheme, saveTheme, type ThemePrefs,
} from "../../engine/theme.js";
import { h } from "../dom.js";
import { iconEl, type IconName } from "../icons.js";
import { openModal, textField } from "../modal.js";
import { toast } from "../toast.js";

export type BackgroundControl = { enable: () => void; disable: () => void; update: (bg: { radius: number; glow: number; bloom: number }) => void };

let backgroundControl: BackgroundControl | null = null;

export function registerBackground(control: BackgroundControl): void {
  backgroundControl = control;
}

const SLIDERS: Array<{ key: keyof ThemePrefs["glass"]; label: string; min: number; max: number; step: number }> = [
  { key: "strength", label: "Strength", min: 0.2, max: 1.6, step: 0.05 },
  { key: "blur", label: "Blur", min: 0, max: 40, step: 1 },
  { key: "frost", label: "Frost", min: 1, max: 2.2, step: 0.05 },
  { key: "tint", label: "Tint", min: 0, max: 0.6, step: 0.02 },
  { key: "gradient", label: "Gradient", min: 0, max: 1.2, step: 0.05 },
  { key: "opacity", label: "Opacity", min: 0.02, max: 0.35, step: 0.01 },
];

export function openSettings(): void {
  const prefs = loadTheme();
  const modal = openModal("Settings", 780);

  const swatchRow = h("div", { class: "swatch-row" });
  const customInput = h("input", { type: "color", class: "swatch swatch-custom", value: prefs.accent, "aria-label": "Custom accent" }) as HTMLInputElement;

  function commit(): void {
    applyTheme(prefs);
    saveTheme(prefs);
    markActive();
  }

  function markActive(): void {
    swatchRow.querySelectorAll<HTMLElement>(".swatch").forEach((node) => {
      node.classList.toggle("active", node.dataset.color === prefs.accent);
    });
    customInput.classList.toggle("active", !ACCENT_SWATCHES.includes(prefs.accent));
  }

  for (const color of ACCENT_SWATCHES) {
    const swatch = h("button", { class: "swatch", type: "button", style: `background:${color}`, "aria-label": color });
    swatch.dataset.color = color;
    swatch.addEventListener("click", () => {
      prefs.accent = color;
      customInput.value = color;
      commit();
    });
    swatchRow.append(swatch);
  }
  customInput.addEventListener("input", () => {
    prefs.accent = customInput.value;
    commit();
  });
  swatchRow.append(customInput);

  const sliderRows = SLIDERS.map((spec) => {
    const input = h("input", {
      type: "range", min: String(spec.min), max: String(spec.max), step: String(spec.step),
      value: String(prefs.glass[spec.key]),
    }) as HTMLInputElement;
    const value = h("span", { class: "slider-val" }, String(prefs.glass[spec.key]));
    input.addEventListener("input", () => {
      prefs.glass[spec.key] = Number(input.value);
      value.textContent = input.value;
      commit();
    });
    return h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, spec.label), input, value);
  });

  const radiusInput = h("input", { type: "range", min: "0", max: "24", step: "1", value: String(prefs.tileRadius) }) as HTMLInputElement;
  const radiusVal = h("span", { class: "slider-val" }, `${prefs.tileRadius}px`);
  radiusInput.addEventListener("input", () => {
    prefs.tileRadius = Number(radiusInput.value);
    radiusVal.textContent = `${prefs.tileRadius}px`;
    commit();
  });
  const radiusRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Tile corner radius"), radiusInput, radiusVal);

  const PRESETS: Array<{ label: string; glass: ThemePrefs["glass"] }> = [
    { label: "Subtle", glass: { strength: 0.7, blur: 14, frost: 1.1, tint: 0.09, gradient: 0.5, opacity: 0.3 } },
    { label: "Standard", glass: { strength: 1, blur: 36, frost: 1.9, tint: 0.12, gradient: 1, opacity: 0.38 } },
    { label: "Max glass", glass: { strength: 1.5, blur: 36, frost: 2.1, tint: 0.16, gradient: 0.95, opacity: 0.08 } },
  ];
  const presetRow = h("div", { class: "preset-row" }, ...PRESETS.map((preset) => {
    const chip = h("button", { class: "btn", type: "button" }, preset.label);
    chip.addEventListener("click", () => {
      Object.assign(prefs.glass, preset.glass);
      sliderRows.forEach((row, index) => {
        const input = row.querySelector("input") as HTMLInputElement;
        input.value = String(prefs.glass[SLIDERS[index].key]);
        (row.querySelector(".slider-val") as HTMLElement).textContent = input.value;
      });
      commit();
    });
    return chip;
  }));


  const vibTint = h("input", { type: "range", min: "-100", max: "100", step: "1", value: String(prefs.vibTint) }) as HTMLInputElement;
  const vibTintVal = h("span", { class: "slider-val" }, `${prefs.vibTint}%`);
  vibTint.addEventListener("input", () => {
    prefs.vibTint = Number(vibTint.value);
    vibTintVal.textContent = `${prefs.vibTint}%`;
    commit();
  });
  let winTimer: number | undefined;
  function pushWindow(): void {
    window.clearTimeout(winTimer);
    winTimer = window.setTimeout(() => {
      // Fade is page paint (background-only); the shell just keeps the desktop
      // blur radius current & re-asserts the transparent webview backdrop.
      const mode = { blur: prefs.winBlur, clear: true };
      void api("/system/window", { method: "POST", body: JSON.stringify(mode) }).catch(() => undefined);
    }, 80);
  }

  const winFade = h("input", { type: "range", min: "0", max: "100", step: "1", value: String(prefs.fade) }) as HTMLInputElement;
  const winFadeVal = h("span", { class: "slider-val" }, `${prefs.fade}%`);
  winFade.addEventListener("input", () => {
    prefs.fade = Number(winFade.value);
    winFadeVal.textContent = `${prefs.fade}%`;
    pushWindow();
    commit();
  });
  const bgFadeRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Fade amount"), winFade, winFadeVal);

  const winBlur = h("input", { type: "range", min: "0", max: "64", step: "1", value: String(prefs.winBlur) }) as HTMLInputElement;
  const winBlurVal = h("span", { class: "slider-val" }, `${prefs.winBlur}px`);
  winBlur.addEventListener("input", () => {
    prefs.winBlur = Number(winBlur.value);
    winBlurVal.textContent = `${prefs.winBlur}px`;
    pushWindow();
    commit();
  });
  const winFrost = h("input", { type: "range", min: "0", max: "100", step: "1", value: String(prefs.winFrost) }) as HTMLInputElement;
  const winFrostVal = h("span", { class: "slider-val" }, String(prefs.winFrost));
  winFrost.addEventListener("input", () => {
    prefs.winFrost = Number(winFrost.value);
    winFrostVal.textContent = String(prefs.winFrost);
    commit();
  });


  const winFrostRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Fade frost"), winFrost, winFrostVal);

  const winBlurRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Fade blur"), winBlur, winBlurVal);
  const winNote = h("p", { class: "settings-hint" }, "Fade amount fades ONLY the app background: 0% is solid, 100% is the bare blurred desktop, & photos, videos, text, icons & panels stay fully solid at every setting. Fade blur sets how strongly that desktop is blurred (Terminal uses about 13). Fade tint recolours the remaining paint (below 0% paints light instead of dark) & Fade frost lifts it toward white. If the bottom corners ever look a hair off against the titlebar, the page's own corner radius is the --win-radius token, one value away.");
  const winDiag = h("p", { class: "settings-hint" }, "");
  void api<{ diag: string }>("/system/glass").then((res) => {
    if (res.diag) winDiag.textContent = `Shell: ${res.diag}`;
  }).catch(() => undefined);


  const vibTintRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Fade tint"), vibTint, vibTintVal);

  interface ThemePreset { name: string; prefs: ThemePrefs }
  const presetList = h("div", { class: "preset-list" });
  const presetName = h("input", { type: "text", class: "text-field", placeholder: "Preset name" }) as HTMLInputElement;
  const presetSave = h("button", { class: "btn primary", type: "button" }, "Save preset");
  function readPresets(): ThemePreset[] {
    return prefGet<ThemePreset[]>("themePresets", []);
  }
  function renderPresets(): void {
    const items = readPresets().map((preset) => {
      const applyBtn = h("button", { class: "btn", type: "button" }, "Apply");
      applyBtn.addEventListener("click", () => {
        Object.assign(prefs, JSON.parse(JSON.stringify(preset.prefs)) as ThemePrefs);
        commit();
        pushWindow();
        toast(`Preset "${preset.name}" applied`);
        modal.close();
      });
      const delBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Delete preset" }, iconEl("trash"));
      delBtn.addEventListener("click", () => {
        prefSet("themePresets", readPresets().filter((entry) => entry.name !== preset.name));
        renderPresets();
      });
      return h("div", { class: "preset-row" }, h("span", { class: "preset-name" }, preset.name), applyBtn, delBtn);
    });
    presetList.replaceChildren(...(items.length ? items : [h("p", { class: "settings-hint" }, "No presets saved yet. Dial in a look, name it & save it here; every appearance, fade, glass, side panel, top bar & background setting is captured.")]));
  }
  presetSave.addEventListener("click", () => {
    const name = presetName.value.trim();
    if (!name) {
      toast("Give the preset a name first");
      return;
    }
    const rest = readPresets().filter((entry) => entry.name !== name);
    prefSet("themePresets", [...rest, { name, prefs: JSON.parse(JSON.stringify(prefs)) as ThemePrefs }]);
    presetName.value = "";
    toast(`Preset "${name}" saved`);
    renderPresets();
  });
  renderPresets();
  const presetBar = h("div", { class: "preset-bar" }, presetName, presetSave);

  const sideOpacity = h("input", { type: "range", min: "0", max: "100", step: "1", value: String(prefs.side.opacity) }) as HTMLInputElement;
  const sideOpacityVal = h("span", { class: "slider-val" }, `${prefs.side.opacity}%`);
  sideOpacity.addEventListener("input", () => {
    prefs.side.opacity = Number(sideOpacity.value);
    sideOpacityVal.textContent = `${prefs.side.opacity}%`;
    commit();
  });
  const sideOpacityRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Panel opacity"), sideOpacity, sideOpacityVal);

  const sideBlur = h("input", { type: "range", min: "0", max: "64", step: "1", value: String(prefs.side.blur) }) as HTMLInputElement;
  const sideBlurVal = h("span", { class: "slider-val" }, `${prefs.side.blur}px`);
  sideBlur.addEventListener("input", () => {
    prefs.side.blur = Number(sideBlur.value);
    sideBlurVal.textContent = `${prefs.side.blur}px`;
    commit();
  });
  const sideBlurRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Panel blur"), sideBlur, sideBlurVal);
  const topOpacity = h("input", { type: "range", min: "0", max: "100", step: "1", value: String(prefs.top.opacity) }) as HTMLInputElement;
  const topOpacityVal = h("span", { class: "slider-val" }, `${prefs.top.opacity}%`);
  topOpacity.addEventListener("input", () => {
    prefs.top.opacity = Number(topOpacity.value);
    topOpacityVal.textContent = `${prefs.top.opacity}%`;
    commit();
  });
  const topOpacityRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Top bar opacity"), topOpacity, topOpacityVal);

  const topBlur = h("input", { type: "range", min: "0", max: "64", step: "1", value: String(prefs.top.blur) }) as HTMLInputElement;
  const topBlurVal = h("span", { class: "slider-val" }, `${prefs.top.blur}px`);
  topBlur.addEventListener("input", () => {
    prefs.top.blur = Number(topBlur.value);
    topBlurVal.textContent = `${prefs.top.blur}px`;
    commit();
  });
  const topBlurRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Top bar blur"), topBlur, topBlurVal);
  const topNote = h("p", { class: "settings-hint" }, "The top bar is its own glass on every page: opacity sets its smoke, blur sets how strongly content scrolling beneath it defocuses. Defaults match the app glass exactly, so nothing changes until you move these.");

  const sideNote = h("p", { class: "settings-hint" }, "These controls shape the side panel ON THE COLLECTIONS PAGE ONLY, where carousels slide beneath it: Panel opacity sets how solid its smoke is there (0% clear glass, 100% nearly solid) & Panel blur sets how strongly photos, videos & text passing under it defocus. Everywhere else the panel simply follows the Liquid glass sliders. Content is SUPPOSED to blur under this panel on Collections; the no-blur rule protects content from the window fade only.");

  const bgCheck = h("input", { type: "checkbox" }) as HTMLInputElement;
  bgCheck.checked = prefs.background;

  const bgRadius = h("input", { type: "range", min: "120", max: "520", step: "10", value: String(prefs.bg.radius) }) as HTMLInputElement;
  const bgRadiusVal = h("span", { class: "slider-val" }, `${prefs.bg.radius}px`);
  bgRadius.addEventListener("input", () => {
    prefs.bg.radius = Number(bgRadius.value);
    bgRadiusVal.textContent = `${prefs.bg.radius}px`;
    backgroundControl?.update(prefs.bg);
    commit();
  });
  const bgRadiusRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Effect radius"), bgRadius, bgRadiusVal);

  const bgGlow = h("input", { type: "range", min: "0", max: "200", step: "1", value: String(prefs.bg.glow) }) as HTMLInputElement;
  const bgGlowVal = h("span", { class: "slider-val" }, String(prefs.bg.glow));
  bgGlow.addEventListener("input", () => {
    prefs.bg.glow = Number(bgGlow.value);
    bgGlowVal.textContent = String(prefs.bg.glow);
    backgroundControl?.update(prefs.bg);
    commit();
  });
  const bgGlowRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Glow (hex lines)"), bgGlow, bgGlowVal);

  const bgBloom = h("input", { type: "range", min: "0", max: "200", step: "1", value: String(prefs.bg.bloom) }) as HTMLInputElement;
  const bgBloomVal = h("span", { class: "slider-val" }, String(prefs.bg.bloom));
  bgBloom.addEventListener("input", () => {
    prefs.bg.bloom = Number(bgBloom.value);
    bgBloomVal.textContent = String(prefs.bg.bloom);
    backgroundControl?.update(prefs.bg);
    commit();
  });
  const bgBloomRow = h("label", { class: "slider-row" }, h("span", { class: "slider-label" }, "Bloom (light wash)"), bgBloom, bgBloomVal);
  const bgNote = h("p", { class: "settings-hint" }, "Glow drives the lit hexagon lines (past 100 the lines thicken too); Bloom drives the soft light wash. Both follow your accent color instantly.");
  bgCheck.addEventListener("change", () => {
    prefs.background = bgCheck.checked;
    if (bgCheck.checked) backgroundControl?.enable();
    else backgroundControl?.disable();
    commit();
  });

  const resetBtn = h("button", { class: "btn", type: "button" }, "Reset theme");
  resetBtn.addEventListener("click", () => {
    Object.assign(prefs, { accent: DEFAULT_THEME.accent, background: true, vibrancy: true, vibTint: DEFAULT_THEME.vibTint, winFrost: DEFAULT_THEME.winFrost, winBlur: DEFAULT_THEME.winBlur, fade: 0, tileRadius: DEFAULT_THEME.tileRadius });
    winFade.value = "0";
    winFadeVal.textContent = "0%";
    pushWindow();
    prefs.side = { ...DEFAULT_THEME.side };
    sideOpacity.value = String(prefs.side.opacity);
    sideOpacityVal.textContent = `${prefs.side.opacity}%`;
    sideBlur.value = String(prefs.side.blur);
    sideBlurVal.textContent = `${prefs.side.blur}px`;
    prefs.top = { ...DEFAULT_THEME.top };
    topOpacity.value = String(prefs.top.opacity);
    topOpacityVal.textContent = `${prefs.top.opacity}%`;
    topBlur.value = String(prefs.top.blur);
    topBlurVal.textContent = `${prefs.top.blur}px`;
    radiusInput.value = String(prefs.tileRadius);
    radiusVal.textContent = `${prefs.tileRadius}px`;
    Object.assign(prefs.glass, DEFAULT_THEME.glass);
    customInput.value = prefs.accent;
    bgCheck.checked = true;
    backgroundControl?.enable();
    sliderRows.forEach((row, index) => {
      const input = row.querySelector("input") as HTMLInputElement;
      input.value = String(prefs.glass[SLIDERS[index].key]);
      (row.querySelector(".slider-val") as HTMLElement).textContent = input.value;
    });
    commit();
  });

  const libraryInfo = h("div", { class: "settings-paths" }, "Loading library info...");
  void api<{ library: string; db: string; models: string }>("/health").then((info) => {
    libraryInfo.replaceChildren(
      h("div", { class: "path-row" }, h("span", { class: "path-k" }, "Library"), h("code", { class: "path-v" }, info.library)),
      h("div", { class: "path-row" }, h("span", { class: "path-k" }, "Database"), h("code", { class: "path-v" }, info.db)),
      h("div", { class: "path-row" }, h("span", { class: "path-k" }, "Models"), h("code", { class: "path-v" }, info.models)),
    );
  });

  const keychainWrap = h("div", { class: "settings-keychain" });
  void api<{ available: boolean; stored: boolean }>("/vault/keychain/status").then((status) => {
    if (!status.available) {
      keychainWrap.append(h("p", { class: "settings-hint" },
        "macOS Keychain unlock is available in the desktop app on a Mac. Native Touch ID prompts land w/ the signed build."));
      return;
    }
    const state = h("p", { class: "settings-hint" },
      status.stored
        ? "A DAM vault passkey is stored in your Keychain. Unlock prompts can use it (Touch ID via Keychain access control)."
        : "Store the vault passkey in your macOS Keychain to unlock w/o typing it.");
    const enableBtn = h("button", { class: "btn", type: "button" }, iconEl("lock"), status.stored ? "Update Keychain entry" : "Enable Keychain unlock");
    enableBtn.addEventListener("click", () => {
      const sub = openModal("Store passkey in Keychain");
      const { wrap, input } = textField("Vault passkey", "password", "Current vault passkey");
      const go = h("button", { class: "btn primary", type: "button" }, "Store");
      go.addEventListener("click", async () => {
        try {
          await api("/vault/keychain/enable", { method: "POST", body: JSON.stringify({ passkey: input.value }) });
          sub.close();
          toast("Stored in the macOS Keychain");
        } catch (err) {
          toast(String((err as Error).message), "error");
        }
      });
      sub.body.append(wrap, h("div", { class: "modal-actions" }, go));
      input.focus();
    });
    keychainWrap.append(state, enableBtn);
  });

  const menubarCheck = h("input", { type: "checkbox" }) as HTMLInputElement;
  const hudCheck = h("input", { type: "checkbox" }) as HTMLInputElement;
  hudCheck.checked = prefGet<boolean>("preloadHud", false);
  hudCheck.addEventListener("change", () => {
    prefSet("preloadHud", hudCheck.checked);
    setPreloadHud(hudCheck.checked);
  });
  void api<{ enabled: boolean }>("/system/menubar").then((res) => {
    menubarCheck.checked = res.enabled;
  }).catch(() => undefined);
  menubarCheck.addEventListener("change", async () => {
    try {
      await api("/system/menubar", { method: "POST", body: JSON.stringify({ enabled: menubarCheck.checked }) });
      toast(menubarCheck.checked
        ? "Menu bar icon enabled; closing the window keeps DAM running for quick imports"
        : "Menu bar icon disabled");
    } catch (err) {
      toast(String((err as Error).message), "error");
    }
  });

  const PANES: Array<{ key: string; label: string; icon: IconName; nodes: HTMLElement[] }> = [
    { key: "appearance", label: "Appearance", icon: "glass", nodes: [
      h("p", { class: "settings-section" }, "Accent color"),
      swatchRow,
      h("p", { class: "settings-section" }, "Liquid glass"),
      presetRow,
      ...sliderRows,
      radiusRow,
      h("p", { class: "settings-section" }, "Window fade"),
      bgFadeRow,
      vibTintRow,
      winFrostRow,
      winBlurRow,
      winNote,
      winDiag,
      h("p", { class: "settings-section" }, "Saved presets"),
      presetBar,
      presetList,
      h("div", { class: "modal-actions", style: "justify-content:flex-start" }, resetBtn),
    ] },
    { key: "sidepanel", label: "Side panel", icon: "panel", nodes: [
      h("p", { class: "settings-section" }, "Panel glass"),
      sideOpacityRow,
      sideBlurRow,
      sideNote,
      h("p", { class: "settings-section" }, "Top bar glass"),
      topOpacityRow,
      topBlurRow,
      topNote,
    ] },
    { key: "background", label: "Background", icon: "sparkle", nodes: [
      h("label", { class: "field-check" }, bgCheck, "Interactive hexagon background"),
      bgRadiusRow,
      bgGlowRow,
      bgBloomRow,
      bgNote,
    ] },
    { key: "app", label: "App", icon: "gear", nodes: [
      h("label", { class: "field-check" }, menubarCheck, "Show the menu bar icon (import photos, videos & folders even while the window is closed)"),
      h("p", { class: "settings-hint" }, "The menu bar icon offers Import Photos & Videos..., Import Folder... & Open DAM. While it is enabled, closing the window hides DAM instead of quitting; quit from the menu bar."),
      h("label", { class: "field-check" }, hudCheck, "Show preload diagnostics (small live readout, bottom-right: pending tiles, queue, requests in flight, loaded runway ahead & behind in px, average load time)"),
      h("p", { class: "settings-hint" }, "If scrolling ever shows tiles loading in, screenshot that readout mid-scroll: it names the failing stage exactly. ahead & behind sitting at the full 13-row figure means the runway is genuinely loaded."),
    ] },
    { key: "library", label: "Library", icon: "library", nodes: [libraryInfo] },
    { key: "vault", label: "Vault & Keychain", icon: "lock", nodes: [keychainWrap] },
  ];

  const paneEls = new Map<string, HTMLElement>();
  const navBtns = new Map<string, HTMLElement>();
  const nav = h("div", { class: "settings-nav" });
  const paneHost = h("div", { class: "settings-panes", style: "flex:1;min-width:0" });
  const activate = (key: string) => {
    prefSet("settingsTab", key);
    for (const [k, el] of paneEls) el.classList.toggle("hidden", k !== key);
    for (const [k, btn] of navBtns) btn.classList.toggle("active", k === key);
  };
  for (const pane of PANES) {
    const el = h("div", { class: "settings-pane hidden" }, ...pane.nodes);
    paneEls.set(pane.key, el);
    paneHost.append(el);
    const btn = h("button", { type: "button" }, iconEl(pane.icon), pane.label);
    btn.addEventListener("click", () => activate(pane.key));
    navBtns.set(pane.key, btn);
    nav.append(btn);
  }
  modal.body.append(h("div", { class: "settings-shell" }, nav, paneHost));
  const savedTab = prefGet<string | null>("settingsTab", null);
  activate(paneEls.has(savedTab ?? "") ? (savedTab as string) : "appearance");
}
