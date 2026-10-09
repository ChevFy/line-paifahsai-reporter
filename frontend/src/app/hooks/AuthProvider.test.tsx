import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { adminRequest } from "../services/api-client";
import { ApiError } from "../utils/api-error";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "./useAuth";

const { getCurrentAdmin, login, logout } = vi.hoisted(() => ({
  getCurrentAdmin: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("../services/auth-service", () => ({ getCurrentAdmin, login, logout }));

const admin = { id: 1, username: "admin", last_login_at: null };

function Probe() {
  const { state, signIn, signOut, retry } = useAuth();
  return (
    <div>
      <p data-testid="state">{JSON.stringify(state)}</p>
      <button type="button" onClick={() => void signIn({ username: "admin", password: "pw" }).catch(() => undefined)}>
        signIn
      </button>
      <button type="button" onClick={() => void signOut().catch(() => undefined)}>
        signOut
      </button>
      <button type="button" onClick={() => void retry()}>
        retry
      </button>
    </div>
  );
}

function renderProvider() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

function currentState() {
  return JSON.parse(screen.getByTestId("state").textContent ?? "null") as Record<string, unknown>;
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  // Unmount before resetting mocks so no effect runs against reset (undefined) mocks
  cleanup();
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe("AuthProvider", () => {
  it("starts in checking and becomes signed-in when /admin/me returns an admin", async () => {
    let resolve!: (value: typeof admin) => void;
    getCurrentAdmin.mockReturnValue(new Promise((r) => (resolve = r)));
    renderProvider();

    expect(currentState()).toEqual({ kind: "checking" });
    await act(async () => resolve(admin));
    expect(currentState()).toEqual({ kind: "signed-in", admin });
  });

  it("becomes signed-out (not expired) when there is no session", async () => {
    getCurrentAdmin.mockResolvedValue(null);
    renderProvider();
    await waitFor(() => expect(currentState()).toEqual({ kind: "signed-out", sessionExpired: false }));
  });

  it("becomes error with the message when the check fails, and retry recovers", async () => {
    getCurrentAdmin.mockRejectedValueOnce(new ApiError(503, "ระบบขัดข้อง"));
    renderProvider();
    await waitFor(() => expect(currentState()).toEqual({ kind: "error", message: "ระบบขัดข้อง" }));

    let resolve!: (value: typeof admin) => void;
    getCurrentAdmin.mockReturnValueOnce(new Promise((r) => (resolve = r)));
    await userEvent.click(screen.getByRole("button", { name: "retry" }));
    expect(currentState()).toEqual({ kind: "checking" });

    await act(async () => resolve(admin));
    expect(currentState()).toEqual({ kind: "signed-in", admin });
    expect(getCurrentAdmin).toHaveBeenCalledTimes(2);
  });

  it("uses the fallback message when the failure has no message", async () => {
    getCurrentAdmin.mockRejectedValue("boom");
    renderProvider();
    await waitFor(() =>
      expect(currentState()).toEqual({ kind: "error", message: "ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ" }),
    );
  });

  it("signIn calls login and switches to signed-in", async () => {
    getCurrentAdmin.mockResolvedValue(null);
    login.mockResolvedValue(admin);
    renderProvider();
    await waitFor(() => expect(currentState().kind).toBe("signed-out"));

    await userEvent.click(screen.getByRole("button", { name: "signIn" }));
    expect(login).toHaveBeenCalledWith({ username: "admin", password: "pw" });
    await waitFor(() => expect(currentState()).toEqual({ kind: "signed-in", admin }));
  });

  it("signIn failure keeps the state signed-out", async () => {
    getCurrentAdmin.mockResolvedValue(null);
    login.mockRejectedValue(new ApiError(401, "รหัสผ่านไม่ถูกต้อง"));
    renderProvider();
    await waitFor(() => expect(currentState().kind).toBe("signed-out"));

    await userEvent.click(screen.getByRole("button", { name: "signIn" }));
    expect(currentState()).toEqual({ kind: "signed-out", sessionExpired: false });
  });

  it("signOut calls logout and switches to signed-out (not expired)", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    logout.mockResolvedValue(undefined);
    renderProvider();
    await waitFor(() => expect(currentState().kind).toBe("signed-in"));

    await userEvent.click(screen.getByRole("button", { name: "signOut" }));
    expect(logout).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(currentState()).toEqual({ kind: "signed-out", sessionExpired: false }));
  });

  it("signOut failure keeps the admin signed in", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    logout.mockRejectedValue(new ApiError(0, "network"));
    renderProvider();
    await waitFor(() => expect(currentState().kind).toBe("signed-in"));

    await userEvent.click(screen.getByRole("button", { name: "signOut" }));
    expect(currentState()).toEqual({ kind: "signed-in", admin });
  });

  it("a 401 from any adminRequest while signed in signs out with sessionExpired=true", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    renderProvider();
    await waitFor(() => expect(currentState().kind).toBe("signed-in"));

    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));
    await act(async () => {
      await adminRequest("/admin/volunteers?limit=50&offset=0");
    });
    expect(currentState()).toEqual({ kind: "signed-out", sessionExpired: true });
  });

  it("a 401 while not signed in does not mark the session as expired", async () => {
    getCurrentAdmin.mockResolvedValue(null);
    renderProvider();
    await waitFor(() => expect(currentState().kind).toBe("signed-out"));

    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));
    await act(async () => {
      await adminRequest("/admin/volunteers");
    });
    expect(currentState()).toEqual({ kind: "signed-out", sessionExpired: false });
  });

  it("unregisters the 401 handler on unmount", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    const { unmount } = renderProvider();
    await waitFor(() => expect(currentState().kind).toBe("signed-in"));
    unmount();

    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));
    const errorSpy = vi.spyOn(console, "error");
    await expect(adminRequest("/admin/volunteers")).resolves.toHaveProperty("status", 401);
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it("useAuth throws outside AuthProvider", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Probe />)).toThrow("useAuth must be used within AuthProvider");
  });
});
