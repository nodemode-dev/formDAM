import { beforeEach, describe, expect, it, vi } from "vitest";

const responses: Array<Record<string, unknown>> = [];
vi.stubGlobal("fetch", vi.fn(async () => ({
  ok: true,
  json: async () => responses.shift() ?? {},
})));

import { loadMore, pageFor, parseRoute, state, toggleSelect, clearSelection } from "../src/engine/store.js";

describe("store", () => {
  beforeEach(() => {
    state.pages.clear();
    responses.length = 0;
    clearSelection();
  });

  it("parses hash routes", () => {
    location.hash = "#/album/12";
    expect(parseRoute()).toEqual({ view: "album", param: "12" });
    location.hash = "";
    expect(parseRoute().view).toBe("library");
  });

  it("pages with keyset cursors and dedupes loads", async () => {
    responses.push({
      items: [{ id: 1, created_ts: 100 }, { id: 2, created_ts: 90 }],
      next: { before: 90, before_id: 2 },
    });
    await loadMore("all");
    expect(pageFor("all").items.length).toBe(2);
    expect(pageFor("all").next).toEqual({ before: 90, before_id: 2 });
    responses.push({ items: [{ id: 3, created_ts: 80 }], next: null });
    await loadMore("all");
    expect(pageFor("all").items.map((m) => m.id)).toEqual([1, 2, 3]);
    await loadMore("all");
    expect(pageFor("all").items.length).toBe(3);
  });

  it("tracks selection toggles", () => {
    toggleSelect(5);
    toggleSelect(6);
    toggleSelect(5);
    expect([...state.selection]).toEqual([6]);
  });
});
