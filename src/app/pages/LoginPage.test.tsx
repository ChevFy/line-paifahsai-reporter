import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { AuthProvider } from "../hooks/AuthProvider";
import { ApiError, NETWORK_ERROR_MESSAGE } from "../utils/api-error";
import LoginPage from "./LoginPage";

const { getCurrentAdmin, login, logout } = vi.hoisted(() => ({
  getCurrentAdmin: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("../services/auth-service", () => ({ getCurrentAdmin, login, logout }));

const admin = { id: 1, username: "admin", last_login_at: null };

async function renderLogin() {
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/volunteers" element={<p>volunteers-page</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
  await screen.findByLabelText("ชื่อผู้ใช้");
}

async function fillAndSubmit(username = "admin", password = "secret") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("ชื่อผู้ใช้"), username);
  await user.type(screen.getByLabelText("รหัสผ่าน"), password);
  await user.click(screen.getByRole("button", { name: "เข้าสู่ระบบ" }));
  return user;
}

beforeEach(() => {
  getCurrentAdmin.mockResolvedValue(null);
});

afterEach(() => {
  // Unmount before resetting mocks so no effect runs against reset (undefined) mocks
  cleanup();
  vi.resetAllMocks();
});

describe("LoginPage", () => {
  it("renders labelled inputs and a submit button", async () => {
    await renderLogin();
    expect(screen.getByRole("heading", { name: "ปายฟ้าใส · แอดมิน" })).toBeInTheDocument();
    expect(screen.getByLabelText("รหัสผ่าน")).toHaveAttribute("type", "password");
    expect(screen.queryByText("เซสชันหมดอายุแล้ว กรุณาเข้าสู่ระบบอีกครั้ง")).not.toBeInTheDocument();
  });

  it("does not call login with empty or whitespace-only fields", async () => {
    await renderLogin();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "เข้าสู่ระบบ" }));
    expect(login).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("ชื่อผู้ใช้"), "   ");
    await user.type(screen.getByLabelText("รหัสผ่าน"), "x");
    // jsdom does not block submit on `required` for whitespace, so the JS guard must
    screen.getByRole("button", { name: "เข้าสู่ระบบ" }).closest("form")!.requestSubmit();
    expect(login).not.toHaveBeenCalled();
  });

  it("trims the username and sends the password as typed", async () => {
    login.mockResolvedValue(admin);
    await renderLogin();
    await fillAndSubmit("  admin  ", " pw ");
    expect(login).toHaveBeenCalledWith({ username: "admin", password: " pw " });
    expect(await screen.findByText("volunteers-page")).toBeInTheDocument();
  });

  it("disables the form while signing in and does not double submit", async () => {
    let resolve!: (value: typeof admin) => void;
    login.mockReturnValue(new Promise((r) => (resolve = r)));
    await renderLogin();
    const user = await fillAndSubmit();

    const busyButton = screen.getByRole("button", { name: "กำลังเข้าสู่ระบบ..." });
    expect(busyButton).toBeDisabled();
    expect(screen.getByLabelText("ชื่อผู้ใช้")).toBeDisabled();
    expect(screen.getByLabelText("รหัสผ่าน")).toBeDisabled();

    await user.click(busyButton);
    busyButton.closest("form")!.requestSubmit();
    expect(login).toHaveBeenCalledTimes(1);

    await act(async () => resolve(admin));
    expect(await screen.findByText("volunteers-page")).toBeInTheDocument();
  });

  it("shows the backend error, clears the password, keeps the username and re-enables the form", async () => {
    login.mockRejectedValue(new ApiError(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"));
    await renderLogin();
    await fillAndSubmit("admin", "wrong");

    expect(await screen.findByRole("alert")).toHaveTextContent("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง");
    expect(screen.getByLabelText("รหัสผ่าน")).toHaveValue("");
    expect(screen.getByLabelText("ชื่อผู้ใช้")).toHaveValue("admin");
    expect(screen.getByRole("button", { name: "เข้าสู่ระบบ" })).toBeEnabled();
  });

  it("shows the network error message", async () => {
    login.mockRejectedValue(new ApiError(0, NETWORK_ERROR_MESSAGE));
    await renderLogin();
    await fillAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent(NETWORK_ERROR_MESSAGE);
  });

  it("a non-ApiError (e.g. a JSON SyntaxError) shows the fallback text, not the raw message", async () => {
    login.mockRejectedValue(new SyntaxError("Unexpected token '<', \"<!doctype \"... is not valid JSON"));
    await renderLogin();
    await fillAndSubmit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("เข้าสู่ระบบไม่สำเร็จ");
    expect(alert).not.toHaveTextContent("Unexpected token");
    expect(screen.getByRole("button", { name: "เข้าสู่ระบบ" })).toBeEnabled();
  });

  it("clears the previous error when retrying and succeeds", async () => {
    login.mockRejectedValueOnce(new ApiError(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")).mockResolvedValueOnce(admin);
    await renderLogin();
    const user = await fillAndSubmit("admin", "wrong");
    await screen.findByRole("alert");

    await user.type(screen.getByLabelText("รหัสผ่าน"), "right");
    await user.click(screen.getByRole("button", { name: "เข้าสู่ระบบ" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(await screen.findByText("volunteers-page")).toBeInTheDocument();
    expect(login).toHaveBeenLastCalledWith({ username: "admin", password: "right" });
  });
});
