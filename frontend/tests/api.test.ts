import { describe, expect, it, vi } from "vitest";

const calls: Array<{ url: string; init: RequestInit }> = [];
vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
  calls.push({ url, init });
  return { ok: true, json: async () => ({ ok: true }) };
}));

import { api, authHeaders, setAlbumToken, setVaultToken } from "../src/engine/api.js";

describe("api client", () => {
  it("always sends the local header", async () => {
    await api("/health");
    const headers = calls.at(-1)!.init.headers as Record<string, string>;
    expect(headers["x-dam-local"]).toBe("1");
    expect(calls.at(-1)!.url).toBe("/api/health");
  });

  it("prefers album tokens then falls back to vault", () => {
    setVaultToken("vault-token");
    expect(authHeaders()["x-dam-vault"]).toBe("vault-token");
    setAlbumToken(9, "album-token");
    expect(authHeaders(9)["x-dam-vault"]).toBe("album-token");
    expect(authHeaders(4)["x-dam-vault"]).toBe("vault-token");
  });
});
