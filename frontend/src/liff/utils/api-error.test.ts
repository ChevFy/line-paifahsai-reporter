import { describe, expect, it } from "vitest";
import { getApiError } from "./api-error";
import { AppError } from "./app-error";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 400 });
}

describe("getApiError", () => {
  it("uses the backend message when present", async () => {
    const error = await getApiError(jsonResponse({ detail: { message: "อยู่นอกพื้นที่" } }), "submit");
    expect(error).not.toBeInstanceOf(AppError);
    expect(error.message).toBe("อยู่นอกพื้นที่");
  });

  it("falls back to an AppError when the body has no message", async () => {
    const error = await getApiError(jsonResponse({}), "submit");
    expect(error).toBeInstanceOf(AppError);
    expect((error as AppError).code).toBe("submit");
  });

  it("falls back to an AppError when the body is not JSON", async () => {
    const error = await getApiError(new Response("<html>502</html>", { status: 502 }), "upload");
    expect((error as AppError).code).toBe("upload");
  });
});
