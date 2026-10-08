import { describe, expect, it } from "vitest";
import { isValidThaiPhone, normalizeThaiPhone } from "./phone";

describe("normalizeThaiPhone", () => {
  it.each([
    ["0812345678", "0812345678"],
    ["081-234-5678", "0812345678"],
    [" 081 234 5678 ", "0812345678"],
    ["(053) 699-123", "053699123"],
    ["+66 81 234 5678", "0812345678"],
    ["+6653699123", "053699123"],
  ])("%s -> %s", (input, expected) => {
    expect(normalizeThaiPhone(input)).toBe(expected);
  });
});

describe("isValidThaiPhone (mirrors backend ^0[0-9]{8,9}$)", () => {
  it.each(["053699123", "0812345678"])("accepts %s", (phone) => {
    expect(isValidThaiPhone(phone)).toBe(true);
  });

  it.each(["", "812345678", "08123456", "08123456789", "08l2345678", "+66812345678"])(
    "rejects %s",
    (phone) => {
      expect(isValidThaiPhone(phone)).toBe(false);
    },
  );
});
