import { describe, expect, it } from "vitest";
import en from "../locales/en.json";
import th from "../locales/th.json";
import { AppError, formatError, toDisplayError } from "./app-error";

describe("toDisplayError", () => {
  it("keeps the code of an AppError", () => {
    expect(toDisplayError(new AppError("network"), "submit")).toEqual({ code: "network" });
  });

  it("keeps the message of a plain Error (backend message)", () => {
    expect(toDisplayError(new Error("จุดนี้อยู่นอกพื้นที่"), "submit")).toEqual({
      message: "จุดนี้อยู่นอกพื้นที่",
    });
  });

  it("falls back to the given code for unknown values", () => {
    expect(toDisplayError("boom", "upload")).toEqual({ code: "upload" });
    expect(toDisplayError(new Error(""), "upload")).toEqual({ code: "upload" });
  });
});

describe("formatError", () => {
  it("translates a code with the current language", () => {
    expect(formatError({ code: "submit" }, th)).toBe(th.errors.submit);
    expect(formatError({ code: "submit" }, en)).toBe(en.errors.submit);
  });

  it("returns a raw message unchanged", () => {
    expect(formatError({ message: "server says no" }, en)).toBe("server says no");
  });
});
