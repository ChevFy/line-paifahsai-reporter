import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../utils/api-error";
import { setUnauthorizedHandler } from "./api-client";
import { changeVolunteerStatus, listVolunteers } from "./volunteer-service";

const volunteer = {
  id: 7,
  full_name: "สมชาย ใจดี",
  phone: "0812345678",
  district_code: "5803",
  status: "approved",
  approved_at: "2026-10-08T07:00:00Z",
  created_at: "2026-10-01T07:00:00Z",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestedUrl(call = 0) {
  return new URL(String(fetchMock.mock.calls[call][0]), "http://localhost");
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

describe("listVolunteers", () => {
  const page = { items: [volunteer], total: 1, limit: 50, offset: 0 };

  it("always sends limit and offset, and omits status/district_code when not set", async () => {
    fetchMock.mockResolvedValue(jsonResponse(page));

    await expect(
      listVolunteers({ status: null, districtCode: null, limit: 50, offset: 100 }),
    ).resolves.toEqual(page);

    const url = requestedUrl();
    expect(url.pathname).toBe("/admin/volunteers");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.get("offset")).toBe("100");
    expect(url.searchParams.has("status")).toBe(false);
    expect(url.searchParams.has("district_code")).toBe(false);
    const init = fetchMock.mock.calls[0][1];
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("sends offset=0 explicitly", async () => {
    fetchMock.mockResolvedValue(jsonResponse(page));
    await listVolunteers({ status: null, districtCode: null, limit: 50, offset: 0 });
    expect(requestedUrl().searchParams.get("offset")).toBe("0");
  });

  it("adds status and district_code when set", async () => {
    fetchMock.mockResolvedValue(jsonResponse(page));

    await listVolunteers({ status: "pending", districtCode: "5803", limit: 50, offset: 0 });

    const url = requestedUrl();
    expect(url.searchParams.get("status")).toBe("pending");
    expect(url.searchParams.get("district_code")).toBe("5803");
  });

  it("throws the backend message on error", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: { message: "สถานะไม่ถูกต้อง" } }, 422));
    await expect(
      listVolunteers({ status: null, districtCode: null, limit: 50, offset: 0 }),
    ).rejects.toMatchObject({ status: 422, message: "สถานะไม่ถูกต้อง" });
  });

  it("falls back to a generic message when the body is unusable", async () => {
    fetchMock.mockResolvedValue(new Response("oops", { status: 500 }));
    await expect(
      listVolunteers({ status: null, districtCode: null, limit: 50, offset: 0 }),
    ).rejects.toMatchObject({ status: 500, message: "โหลดรายชื่อจิตอาสาไม่สำเร็จ" });
  });

  it("fires the unauthorized handler on 401 and throws ApiError(401)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: { message: "เซสชันหมดอายุ" } }, 401));

    const error = await listVolunteers({ status: null, districtCode: null, limit: 50, offset: 0 }).catch(
      (reason: unknown) => reason,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("throws a network ApiError when fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(
      listVolunteers({ status: null, districtCode: null, limit: 50, offset: 0 }),
    ).rejects.toMatchObject({ status: 0 });
  });
});

describe("changeVolunteerStatus", () => {
  it.each(["approve", "reject", "suspend"] as const)("POSTs to /admin/volunteers/{id}/%s", async (action) => {
    fetchMock.mockResolvedValue(jsonResponse(volunteer));

    await expect(changeVolunteerStatus(7, action)).resolves.toEqual(volunteer);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/admin/volunteers/7/${action}`);
    expect(init?.method).toBe("POST");
  });

  it("throws the backend 404 message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: { message: "ไม่พบจิตอาสา" } }, 404));
    await expect(changeVolunteerStatus(99, "approve")).rejects.toMatchObject({
      status: 404,
      message: "ไม่พบจิตอาสา",
    });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the body is unusable", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 500 }));
    await expect(changeVolunteerStatus(7, "suspend")).rejects.toMatchObject({
      message: "เปลี่ยนสถานะจิตอาสาไม่สำเร็จ",
    });
  });

  it("fires the unauthorized handler on 401", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 401 }));
    await expect(changeVolunteerStatus(7, "approve")).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
});
