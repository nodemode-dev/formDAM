import { describe, expect, it } from "vitest";
import { countFmt, dayKey, formatDuration, humanBytes, monthLabel } from "../src/engine/format.js";

describe("format", () => {
  it("formats byte sizes", () => {
    expect(humanBytes(512)).toBe("512 B");
    expect(humanBytes(2048)).toContain("KiB");
  });

  it("formats durations", () => {
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(3671)).toBe("1:01:11");
  });

  it("keys days stably", () => {
    const ts = new Date(2026, 6, 25, 13, 30).getTime() / 1000;
    expect(dayKey(ts)).toBe("2026-07-25");
  });

  it("labels months from periods", () => {
    expect(monthLabel("2026-07")).toContain("2026");
  });

  it("localizes counts", () => {
    expect(countFmt(75301)).toBe((75301).toLocaleString());
  });
});
