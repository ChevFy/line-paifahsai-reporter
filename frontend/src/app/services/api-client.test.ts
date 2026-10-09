import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, NETWORK_ERROR_MESSAGE } from "../utils/api-error";
import { adminRequest, request, setUnauthorizedHandler } from "./api-client";

const fetchMock = vi.fn<typeof fetch>();
const onUnauthorized = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  setUnauthorizedHandler(onUnauthorized);
});

afterEach(() => {
  setUnauthorizedHandler(() => undefined);
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe("request", () => {
  it("passes path and init straight to fetch and returns the response", async () => {
    const response = new Response(null, { status: 204 });
    fetchMock.mockResolvedValue(response);
    const init = { method: "POST" };

    await expect(request("/admin/logout", init)).resolves.toBe(response);
    expect(fetchMock).toHaveBeenCalledWith("/admin/logout", init);
  });

  it("throws ApiError with status 0 and the network message when fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const error = await request("/admin/me").catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, message: NETWORK_ERROR_MESSAGE });
  });

  it("does not call the unauthorized handler on 401", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));

    const response = await request("/admin/me");
    expect(response.status).toBe(401);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe("adminRequest", () => {
  it("calls the registered unauthorized handler on 401 and still returns the response", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));

    const response = await adminRequest("/admin/volunteers");
    expect(response.status).toBe(401);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it.each([200, 403, 404, 500])("does not call the handler on %i", async (status) => {
    fetchMock.mockResolvedValue(new Response(null, { status }));

    await adminRequest("/admin/volunteers");
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("throws a network ApiError without calling the handler when fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(adminRequest("/admin/volunteers")).rejects.toMatchObject({ status: 0 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("uses the latest registered handler", async () => {
    const second = vi.fn();
    setUnauthorizedHandler(second);
    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));

    await adminRequest("/admin/volunteers");
    expect(second).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});
