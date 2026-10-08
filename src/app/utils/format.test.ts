import { describe, expect, it } from "vitest";
import { formatDateTime, formatElapsed, formatTime } from "./format";

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

  it.each(["not-a-date", "2026-13-45T99:00:00Z"])("returns a dash for the unparseable %j instead of throwing", (value) => {
    expect(formatDateTime(value)).toBe("–");
  });
});

describe("formatTime", () => {
  it("formats HH:MM in Asia/Bangkok time", () => {
    // 03:00 UTC = 10:00 in Bangkok
    expect(formatTime("2026-10-09T03:00:00Z")).toBe("10:00");
    // 17:05 UTC = 00:05 the next day in Bangkok
    expect(formatTime("2026-10-09T17:05:00Z")).toBe("00:05");
  });

  it("does not include the date", () => {
    const text = formatTime("2026-03-01T03:30:00Z");
    expect(text).toBe("10:30");
    expect(text).not.toContain("2569");
  });

  it.each([null, "", "not-a-date"])("returns a dash for %j", (value) => {
    expect(formatTime(value)).toBe("–");
  });
});

describe("formatElapsed", () => {
  const rtf = new Intl.RelativeTimeFormat("th-TH", { numeric: "always" });
  const now = new Date("2026-10-09T12:00:00Z");
  const ago = (minutes: number) => new Date(now.getTime() - minutes * 60_000).toISOString();

  it("shows 0 minutes (numeric, not 'นาทีนี้') for the same instant and under a minute", () => {
    expect(formatElapsed(now.toISOString(), now)).toBe("0 นาทีที่ผ่านมา");
    expect(formatElapsed(ago(0.4), now)).toBe("0 นาทีที่ผ่านมา");
    expect(formatElapsed(ago(0.99), now)).toBe("0 นาทีที่ผ่านมา");
  });

  it("uses minutes below one hour, rounding down", () => {
    expect(formatElapsed(ago(1), now)).toBe(rtf.format(-1, "minute"));
    expect(formatElapsed(ago(5), now)).toBe("5 นาทีที่ผ่านมา");
    expect(formatElapsed(ago(5.9), now)).toBe("5 นาทีที่ผ่านมา");
    expect(formatElapsed(ago(59), now)).toBe(rtf.format(-59, "minute"));
  });

  it("switches to hours only at a full 60 minutes and floors the hours", () => {
    expect(formatElapsed(ago(59.99), now)).toBe(rtf.format(-59, "minute"));
    expect(formatElapsed(ago(60), now)).toBe("1 ชั่วโมงที่ผ่านมา");
    expect(formatElapsed(ago(90), now)).toBe(rtf.format(-1, "hour"));
    expect(formatElapsed(ago(119), now)).toBe(rtf.format(-1, "hour"));
    expect(formatElapsed(ago(120), now)).toBe(rtf.format(-2, "hour"));
    expect(formatElapsed(ago(3 * 60), now)).toBe("3 ชั่วโมงที่ผ่านมา");
    expect(formatElapsed(ago(24 * 60 - 1), now)).toBe(rtf.format(-23, "hour"));
  });

  it("switches to days at 24 hours, numeric (no 'เมื่อวาน') and floored", () => {
    expect(formatElapsed(ago(24 * 60), now)).toBe("1 วันที่ผ่านมา");
    expect(formatElapsed(ago(24 * 60), now)).not.toBe("เมื่อวาน");
    expect(formatElapsed(ago(48 * 60 - 1), now)).toBe(rtf.format(-1, "day"));
    expect(formatElapsed(ago(3 * 24 * 60), now)).toBe(rtf.format(-3, "day"));
  });

  it("clamps a timestamp later than now (clock skew) to 0 minutes ago", () => {
    expect(formatElapsed(ago(-5), now)).toBe("0 นาทีที่ผ่านมา");
    expect(formatElapsed(ago(-0.2), now)).toBe("0 นาทีที่ผ่านมา");
    expect(formatElapsed(ago(-5), now)).not.toContain("ในอีก");
  });

  it("accepts a timestamp with a +07:00 offset", () => {
    expect(formatElapsed("2026-10-09T18:50:00+07:00", now)).toBe(rtf.format(-10, "minute"));
  });

  it.each(["not-a-date", ""])("returns a dash for the unparseable %j instead of throwing", (value) => {
    expect(formatElapsed(value, now)).toBe("–");
  });
});
