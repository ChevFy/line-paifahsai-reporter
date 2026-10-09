import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setUnauthorizedHandler } from "./api-client";
import { listActiveIncidents } from "./incident-service";
import { NETWORK_ERROR_MESSAGE } from "../utils/api-error";

const list = {
  generated_at: "2026-10-09T03:00:00Z",
  incidents: [
    {
      id: 7,
      latitude: 19.36,
      longitude: 98.44,
      district_code: "5803",
      status: "open",
      report_count: 2,
      created_at: "2026-10-09T02:30:00Z",
    },
  ],
  truncated: false,
  emergency_phone: "1362",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

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

describe("listActiveIncidents", () => {
  it("GETs /incidents/active without a query when no district is set", async () => {
    fetchMock.mockResolvedValue(jsonResponse(list));

    await expect(listActiveIncidents(null)).resolves.toEqual(list);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/incidents/active");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("an empty district string also sends no query", async () => {
    fetchMock.mockResolvedValue(jsonResponse(list));
    await listActiveIncidents("");
    expect(fetchMock.mock.calls[0][0]).toBe("/incidents/active");
  });

  it("adds district_code when a district is set", async () => {
    fetchMock.mockResolvedValue(jsonResponse(list));
    await listActiveIncidents("5803");
    expect(fetchMock.mock.calls[0][0]).toBe("/incidents/active?district_code=5803");
  });

  it("URL-encodes the district code", async () => {
    fetchMock.mockResolvedValue(jsonResponse(list));
    await listActiveIncidents("58 03&x=1");
    expect(fetchMock.mock.calls[0][0]).toBe("/incidents/active?district_code=58+03%26x%3D1");
  });

  it("sends no credentials-only headers (public endpoint, no Authorization)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(list));
    await listActiveIncidents(null);
    const init = fetchMock.mock.calls[0][1];
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });

  it("throws the backend detail.message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: { message: "รหัสอำเภอไม่ถูกต้อง" } }, 422));
    await expect(listActiveIncidents("x")).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "รหัสอำเภอไม่ถูกต้อง",
    });
  });

  it.each([
    ["non-JSON body", () => new Response("Bad gateway", { status: 502 })],
    ["JSON without detail.message", () => jsonResponse({ detail: "boom" }, 500)],
    ["empty detail.message", () => jsonResponse({ detail: { message: "" } }, 500)],
  ])("falls back to the generic message for %s", async (_label, make) => {
    fetchMock.mockResolvedValue(make());
    await expect(listActiveIncidents(null)).rejects.toMatchObject({
      name: "ApiError",
      message: "โหลดเหตุที่กำลังเกิดไม่สำเร็จ",
    });
  });

  it("is a public endpoint: a 401 does not fire the admin unauthorized handler", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 401 }));
    await expect(listActiveIncidents(null)).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("forwards the AbortSignal to fetch", async () => {
    fetchMock.mockResolvedValue(jsonResponse(list));
    const controller = new AbortController();
    await listActiveIncidents("5803", controller.signal);
    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it("sends no signal when none is given", async () => {
    fetchMock.mockResolvedValue(jsonResponse(list));
    await listActiveIncidents(null);
    expect(fetchMock.mock.calls[0][1]?.signal).toBeUndefined();
  });

  it("an aborted/timed-out fetch becomes a network ApiError (not a raw DOMException)", async () => {
    fetchMock.mockRejectedValue(new DOMException("The operation timed out.", "TimeoutError"));
    const controller = new AbortController();
    await expect(listActiveIncidents(null, controller.signal)).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      message: NETWORK_ERROR_MESSAGE,
    });
  });

  it("throws a network ApiError when fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(listActiveIncidents(null)).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      message: NETWORK_ERROR_MESSAGE,
    });
  });
});
