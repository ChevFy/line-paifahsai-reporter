import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setUnauthorizedHandler } from "./api-client";
import { listDistricts } from "./district-service";

const districts = [
  { code: "5803", name_th: "ปาย", province_name_th: "แม่ฮ่องสอน" },
  { code: "5801", name_th: "เมืองแม่ฮ่องสอน", province_name_th: "แม่ฮ่องสอน" },
];

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

describe("listDistricts", () => {
  it("GETs /districts and returns the list", async () => {
    fetchMock.mockResolvedValue(jsonResponse(districts));

    await expect(listDistricts()).resolves.toEqual(districts);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/districts");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("throws the backend message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: { message: "ระบบขัดข้อง" } }, 500));
    await expect(listDistricts()).rejects.toMatchObject({ status: 500, message: "ระบบขัดข้อง" });
  });

  it("falls back to a generic message when the body is unusable", async () => {
    fetchMock.mockResolvedValue(new Response("Bad gateway", { status: 502 }));
    await expect(listDistricts()).rejects.toMatchObject({
      status: 502,
      message: "โหลดรายชื่ออำเภอไม่สำเร็จ",
    });
  });

  it("is a public endpoint: a 401 does not fire the admin unauthorized handler", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 401 }));
    await expect(listDistricts()).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("throws a network ApiError when fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(listDistricts()).rejects.toMatchObject({ status: 0 });
  });
});
