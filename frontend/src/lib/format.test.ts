import { describe, expect, it } from "vitest";
import { formatWhen, minutes, percent, words } from "./format";

describe("format", () => {
  it("renders London wall time with tabular-friendly text", () => {
    expect(formatWhen("2026-11-02T09:15:00+00:00")).toBe("02 Nov, 09:15");
  });

  it("does not invent a time for an empty value", () => {
    expect(formatWhen(null)).toBe("—");
    expect(percent(null)).toBe("—");
  });

  it("keeps status words readable", () => {
    expect(words("awaiting_fulfilment")).toBe("awaiting fulfilment");
    expect(minutes(150)).toBe("2h 30m");
  });
});
