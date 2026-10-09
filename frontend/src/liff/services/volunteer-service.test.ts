import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../config/api";
import { AppError } from "../utils/app-error";
import { getMyVolunteer, registerVolunteer } from "./volunteer-service";

const { getIDToken } = vi.hoisted(() => ({ getIDToken: vi.fn() }));
vi.mock("../../liff", () => ({ default: { getIDToken } }));

const registration = {
  volunteer: {
    id: 7,
    full_name: "สมชาย ใจดี",
    phone: "0812345678",
    district_code: "5803",
    status: "pending",
    approved_at: null,
    created_at: "2026-10-08T07:00:00Z",
  },
  created: true,
  message: "ลงทะเบียนแล้ว รอแอดมินอนุมัติ",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  getIDToken.mockReturnValue("id-token");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe("registerVolunteer", () => {
  const payload = { full_name: "สมชาย ใจดี", phone: "0812345678", district_code: "5803" };

  it("POSTs JSON to /volunteers with the LINE ID token", async () => {
    fetchMock.mockResolvedValue(jsonResponse(registration));

    await expect(registerVolunteer(payload)).resolves.toEqual(registration);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/volunteers`);
    expect(init?.method).toBe("POST");
    expect(init?.headers).toEqual({
      Authorization: "Bearer id-token",
      "Content-Type": "application/json",
    });
    expect(JSON.parse(init?.body as string)).toEqual(payload);
  });

  it("throws the backend detail.message", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: { message: "ไม่พบอำเภอที่เลือก กรุณาเลือกใหม่" } }, 422),
    );
    await expect(registerVolunteer(payload)).rejects.toThrow("ไม่พบอำเภอที่เลือก กรุณาเลือกใหม่");
  });

  it("falls back to registerVolunteer when the error body is unusable", async () => {
    fetchMock.mockResolvedValue(new Response("Bad gateway", { status: 502 }));
    await expect(registerVolunteer(payload)).rejects.toMatchObject({ code: "registerVolunteer" });
  });

  it("throws a network AppError when fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await registerVolunteer(payload).catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(AppError);
    expect(error).toMatchObject({ code: "network" });
  });

  it("does not call the API without a LINE ID token", async () => {
    getIDToken.mockReturnValue(null);
    await expect(registerVolunteer(payload)).rejects.toMatchObject({ code: "notLoggedIn" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("getMyVolunteer", () => {
  it("GETs /volunteers/me with the LINE ID token", async () => {
    fetchMock.mockResolvedValue(jsonResponse(registration));

    await expect(getMyVolunteer()).resolves.toEqual(registration);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/volunteers/me`);
    expect(init?.method).toBeUndefined();
    expect(init?.headers).toEqual({ Authorization: "Bearer id-token" });
  });

  it("returns null when not registered (404)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: { message: "ยังไม่ได้ลงทะเบียนเป็นจิตอาสา" } }, 404),
    );
    await expect(getMyVolunteer()).resolves.toBeNull();
  });

  it("does not treat an auth failure as not registered", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: { message: "ยืนยันตัวตน LINE ไม่สำเร็จ" } }, 401),
    );
    await expect(getMyVolunteer()).rejects.toThrow("ยืนยันตัวตน LINE ไม่สำเร็จ");
  });
});
