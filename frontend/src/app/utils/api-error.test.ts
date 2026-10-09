import { describe, expect, it } from "vitest";
import { ApiError, errorMessage, readApiError } from "./api-error";

function jsonResponse(body: unknown, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ApiError", () => {
  it("is an Error carrying status and message", () => {
    const error = new ApiError(404, "ไม่พบจิตอาสา");
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.status).toBe(404);
    expect(error.message).toBe("ไม่พบจิตอาสา");
  });
});

describe("readApiError", () => {
  it("uses detail.message and the response status", async () => {
    const error = await readApiError(jsonResponse({ detail: { message: "ไม่พบจิตอาสา" } }, 404), "fallback");
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, message: "ไม่พบจิตอาสา" });
  });

  it.each([
    ["empty message", { detail: { message: "" } }],
    ["non-string message", { detail: { message: 42 } }],
    ["missing detail", { error: "x" }],
    ["FastAPI validation list", { detail: [{ msg: "field required" }] }],
    ["null body", null],
  ])("falls back on %s", async (_label, body) => {
    const error = await readApiError(jsonResponse(body, 422), "fallback");
    expect(error).toMatchObject({ status: 422, message: "fallback" });
  });

  it("falls back when the body is not JSON", async () => {
    const error = await readApiError(new Response("<html>Bad gateway</html>", { status: 502 }), "fallback");
    expect(error).toMatchObject({ status: 502, message: "fallback" });
  });

  it("falls back when the body is empty", async () => {
    const error = await readApiError(new Response(null, { status: 500 }), "fallback");
    expect(error).toMatchObject({ status: 500, message: "fallback" });
  });
});

describe("errorMessage", () => {
  it("returns the ApiError message", () => {
    expect(errorMessage(new ApiError(500, "ระบบขัดข้อง"), "fallback")).toBe("ระบบขัดข้อง");
  });

  it("hides messages of other errors, e.g. a JSON parse error", () => {
    const parseError = new SyntaxError("Unexpected token '<', \"<!doctype \"... is not valid JSON");
    expect(errorMessage(parseError, "fallback")).toBe("fallback");
    expect(errorMessage(new Error("boom"), "fallback")).toBe("fallback");
  });

  it.each([["string", "boom"], ["undefined", undefined], ["object", { message: "x" }], ["empty Error", new Error("")]])(
    "returns the fallback for %s",
    (_label, reason) => {
      expect(errorMessage(reason, "fallback")).toBe("fallback");
    },
  );
});
