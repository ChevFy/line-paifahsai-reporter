import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, NETWORK_ERROR_MESSAGE } from "../utils/api-error";
import { setUnauthorizedHandler } from "./api-client";
import { getCurrentAdmin, login, logout } from "./auth-service";

const admin = { id: 1, username: "admin", last_login_at: "2026-10-08T01:00:00Z" };

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

describe("login", () => {
  const credentials = { username: "admin", password: "secret" };

  it("POSTs JSON credentials to /admin/login without an Authorization header", async () => {
    fetchMock.mockResolvedValue(jsonResponse(admin));

    await expect(login(credentials)).resolves.toEqual(admin);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/admin/login");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init?.body as string)).toEqual(credentials);
  });

  it("surfaces the backend message on 401 and does not fire the unauthorized handler", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: { message: "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง" } }, 401),
    );

    const error = await login(credentials).catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, message: "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง" });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the error body is unusable", async () => {
    fetchMock.mockResolvedValue(new Response("Bad gateway", { status: 502 }));
    await expect(login(credentials)).rejects.toMatchObject({
      status: 502,
      message: "เข้าสู่ระบบไม่สำเร็จ",
    });
  });

  it("throws a network ApiError when fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(login(credentials)).rejects.toMatchObject({
      status: 0,
      message: NETWORK_ERROR_MESSAGE,
    });
  });
});

describe("logout", () => {
  it("POSTs to /admin/logout and resolves on 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(logout()).resolves.toBeUndefined();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/admin/logout");
    expect(init?.method).toBe("POST");
  });

  it("throws the fallback message when logout fails", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 500 }));
    await expect(logout()).rejects.toMatchObject({ status: 500, message: "ออกจากระบบไม่สำเร็จ" });
  });
});

describe("getCurrentAdmin", () => {
  it("GETs /admin/me and returns the admin", async () => {
    fetchMock.mockResolvedValue(jsonResponse(admin));

    await expect(getCurrentAdmin()).resolves.toEqual(admin);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/admin/me");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("returns null on 401 without firing the unauthorized handler", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: { message: "ยังไม่ได้เข้าสู่ระบบ" } }, 401));

    await expect(getCurrentAdmin()).resolves.toBeNull();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("throws the backend message on other errors", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: { message: "ระบบขัดข้อง" } }, 500));
    await expect(getCurrentAdmin()).rejects.toMatchObject({ status: 500, message: "ระบบขัดข้อง" });
  });

  it("throws the fallback message when the error body is unusable", async () => {
    fetchMock.mockResolvedValue(new Response("<html>", { status: 503 }));
    await expect(getCurrentAdmin()).rejects.toMatchObject({
      status: 503,
      message: "ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ",
    });
  });

  it("throws a network ApiError when fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(getCurrentAdmin()).rejects.toMatchObject({ status: 0 });
  });
});
