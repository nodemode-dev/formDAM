import { api } from "./api.js";

let cache: Record<string, unknown> = {};
let saveTimer: number | undefined;

export async function initPrefs(): Promise<void> {
  try {
    const res = await api<{ value: Record<string, unknown> | null }>("/prefs/ui");
    cache = res.value && typeof res.value === "object" ? res.value : {};
  } catch {
    cache = {};
  }
}

export function prefGet<T>(key: string, fallback: T): T {
  const raw = cache[key];
  return raw === undefined ? fallback : (raw as T);
}

export function prefSet(key: string, value: unknown): void {
  cache[key] = value;
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    void api("/prefs/ui", { method: "PUT", body: JSON.stringify({ value: cache }) }).catch(() => undefined);
  }, 250);
}
