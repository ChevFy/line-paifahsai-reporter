import { describe, expect, it } from "vitest";
import en from "./en.json";
import th from "./th.json";

function keys(value: object, prefix = ""): string[] {
  return Object.entries(value).flatMap(([key, child]) =>
    typeof child === "object" && child !== null
      ? keys(child, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

describe("locales", () => {
  it("th and en have the same keys", () => {
    expect(keys(en).sort()).toEqual(keys(th).sort());
  });

  it("has no empty strings", () => {
    for (const locale of [th, en]) {
      for (const key of keys(locale)) {
        const value = key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], locale);
        expect(value, key).not.toBe("");
      }
    }
  });
});
