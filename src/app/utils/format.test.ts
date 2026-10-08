import { describe, expect, it } from "vitest";
import { formatDateTime } from "./format";

describe("formatDateTime", () => {
  it("formats in Thai (Buddhist year) using Asia/Bangkok time", () => {
    // 03:30 UTC = 10:30 in Bangkok
    const text = formatDateTime("2026-03-01T03:30:00Z");
    expect(text).toContain("2569");
    expect(text).toContain("10:30");
    expect(text).toContain("มี.ค.");
  });

  it("rolls over to the next day in Bangkok time", () => {
    // 20:00 UTC on 31 Dec = 03:00 on 1 Jan in Bangkok
    const text = formatDateTime("2026-12-31T20:00:00Z");
    expect(text).toContain("1 ม.ค. 2570");
    expect(text).toContain("03:00");
  });

  it.each([null, ""])("returns a dash for %j", (value) => {
    expect(formatDateTime(value)).toBe("–");
  });

  it("throws RangeError on an unparseable date string", () => {
    expect(() => formatDateTime("not-a-date")).toThrow(RangeError);
  });
});
