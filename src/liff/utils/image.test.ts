import { describe, expect, it } from "vitest";
import { validateImage } from "./image";

function fakeFile(type: string, size: number) {
  const file = new File(["x"], "photo", { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("validateImage", () => {
  it("accepts a small JPEG", () => {
    expect(validateImage(fakeFile("image/jpeg", 1024))).toBeNull();
  });

  it("rejects unsupported types with an error code", () => {
    expect(validateImage(fakeFile("image/gif", 1024))).toBe("imageType");
  });

  it("rejects files over 10 MB with an error code", () => {
    expect(validateImage(fakeFile("image/png", 11 * 1024 * 1024))).toBe("imageSize");
  });
});
