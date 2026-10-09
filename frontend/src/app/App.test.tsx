import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { AdminApp } from "./App";
import { AuthProvider } from "./hooks/AuthProvider";
import { ApiError, NETWORK_ERROR_MESSAGE } from "./utils/api-error";

const { getCurrentAdmin, login, logout } = vi.hoisted(() => ({
  getCurrentAdmin: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("./services/auth-service", () => ({ getCurrentAdmin, login, logout }));

const { listDistricts } = vi.hoisted(() => ({ listDistricts: vi.fn() }));
vi.mock("./services/district-service", () => ({ listDistricts }));

const { listActiveIncidents } = vi.hoisted(() => ({ listActiveIncidents: vi.fn() }));
vi.mock("./services/incident-service", () => ({ listActiveIncidents }));

// Leaflet needs real layout; the map page is only checked for routing here
vi.mock("./components/IncidentMap", () => ({ default: () => null }));

// volunteer-service is kept real (fetch is stubbed) so that a 401 travels
// through adminRequest -> AuthProvider's unauthorized handler like in production.
const fetchMock = vi.fn<typeof fetch>();

const admin = { id: 1, username: "admin", last_login_at: null };
const emptyPage = { items: [], total: 0, limit: 50, offset: 0 };

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function LocationDisplay() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AdminApp />
        <LocationDisplay />
      </AuthProvider>
    </MemoryRouter>,
  );
}

const location = () => screen.getByTestId("location").textContent;

async function logIn() {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("ชื่อผู้ใช้"), "admin");
  await user.type(screen.getByLabelText("รหัสผ่าน"), "secret");
  await user.click(screen.getByRole("button", { name: "เข้าสู่ระบบ" }));
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  listDistricts.mockResolvedValue([]);
  listActiveIncidents.mockResolvedValue({
    generated_at: "2026-10-09T03:00:00Z",
    incidents: [],
    truncated: false,
    emergency_phone: "1362",
  });
  fetchMock.mockImplementation(async () => jsonResponse(emptyPage));
});

afterEach(() => {
  // Unmount before resetting mocks so no effect runs against reset (undefined) mocks
  cleanup();
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe("AdminApp", () => {
  it("shows a checking status while /admin/me is pending", () => {
    getCurrentAdmin.mockReturnValue(new Promise(() => undefined));
    renderAt("/volunteers");
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("กำลังตรวจสอบการเข้าสู่ระบบ...");
    expect(status).toHaveClass("loading-text");
    expect(status.querySelector("svg.spin")).toHaveAttribute("width", "16");
  });

  it("a non-ApiError from /admin/me shows the fallback text on the error screen", async () => {
    getCurrentAdmin.mockRejectedValue(new SyntaxError("Unexpected token '<'"));
    renderAt("/volunteers");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ");
    expect(alert).not.toHaveTextContent("Unexpected token");
    expect(alert.querySelector("svg")).not.toBeNull();
    expect(screen.getByRole("button", { name: "ลองอีกครั้ง" })).toBeEnabled();
  });

  it("redirects an unauthenticated user to /login", async () => {
    getCurrentAdmin.mockResolvedValue(null);
    renderAt("/volunteers");
    expect(await screen.findByLabelText("ชื่อผู้ใช้")).toBeInTheDocument();
    expect(location()).toBe("/login");
  });

  it("after login lands on /volunteers by default", async () => {
    getCurrentAdmin.mockResolvedValue(null);
    login.mockResolvedValue(admin);
    renderAt("/login");
    await logIn();

    expect(await screen.findByRole("heading", { name: "จิตอาสา" })).toBeInTheDocument();
    expect(location()).toBe("/volunteers");
  });

  it("after login returns to the original path including the query string", async () => {
    getCurrentAdmin.mockResolvedValue(null);
    login.mockResolvedValue(admin);
    renderAt("/volunteers?status=approved&page=2");
    await screen.findByLabelText("ชื่อผู้ใช้");
    expect(location()).toBe("/login");

    await logIn();
    expect(await screen.findByRole("heading", { name: "จิตอาสา" })).toBeInTheDocument();
    expect(location()).toBe("/volunteers?status=approved&page=2");
  });

  it("redirects / to /volunteers when signed in", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "จิตอาสา" })).toBeInTheDocument();
    expect(location()).toBe("/volunteers");
    expect(screen.getByText("admin")).toBeInTheDocument();
  });

  it("redirects unknown paths to /volunteers when signed in", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    renderAt("/nope");
    expect(await screen.findByRole("heading", { name: "จิตอาสา" })).toBeInTheDocument();
    expect(location()).toBe("/volunteers");
  });

  it("renders the incidents map page at /map, keeping ?district=", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    renderAt("/map?district=5803");
    expect(await screen.findByRole("heading", { name: "เหตุที่กำลังเกิด" })).toBeInTheDocument();
    expect(location()).toBe("/map?district=5803");
    await waitFor(() => expect(listActiveIncidents).toHaveBeenCalledWith("5803", expect.any(AbortSignal)));
    expect(screen.getByRole("link", { name: "แผนที่เหตุ" })).toHaveAttribute("aria-current", "page");
  });

  it("an unauthenticated visit to /map goes to /login and returns to /map after login", async () => {
    getCurrentAdmin.mockResolvedValue(null);
    login.mockResolvedValue(admin);
    renderAt("/map");
    await screen.findByLabelText("ชื่อผู้ใช้");
    expect(location()).toBe("/login");
    expect(listActiveIncidents).not.toHaveBeenCalled();

    await logIn();
    expect(await screen.findByRole("heading", { name: "เหตุที่กำลังเกิด" })).toBeInTheDocument();
    expect(location()).toBe("/map");
  });

  it("the main nav links to แผนที่เหตุ and จิตอาสา", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    renderAt("/volunteers");
    await screen.findByRole("heading", { name: "จิตอาสา" });
    const nav = screen.getByRole("navigation", { name: "เมนูหลัก" });
    const mapLink = within(nav).getByRole("link", { name: "แผนที่เหตุ" });
    expect(mapLink).toHaveAttribute("href", "/map");
    expect(mapLink).not.toHaveAttribute("aria-current");
    expect(within(nav).getByRole("link", { name: "จิตอาสา" })).toHaveAttribute("aria-current", "page");

    await userEvent.click(mapLink);
    expect(await screen.findByRole("heading", { name: "เหตุที่กำลังเกิด" })).toBeInTheDocument();
    expect(location()).toBe("/map");
    expect(mapLink).toHaveAttribute("aria-current", "page");
  });

  it("a signed-in admin visiting /login is sent to /volunteers", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    renderAt("/login");
    expect(await screen.findByRole("heading", { name: "จิตอาสา" })).toBeInTheDocument();
    expect(location()).toBe("/volunteers");
  });

  it("a 401 from the API while signed in shows the session-expired notice on /login", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    fetchMock.mockImplementation(async () =>
      jsonResponse({ detail: { message: "กรุณาเข้าสู่ระบบ" } }, 401),
    );
    renderAt("/volunteers");

    expect(
      await screen.findByText("เซสชันหมดอายุแล้ว กรุณาเข้าสู่ระบบอีกครั้ง"),
    ).toBeInTheDocument();
    expect(location()).toBe("/login");
    expect(screen.getByLabelText("ชื่อผู้ใช้")).toBeInTheDocument();
  });

  it("signing out returns to /login without the session-expired notice", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    logout.mockResolvedValue(undefined);
    renderAt("/volunteers");
    await userEvent.click(await screen.findByRole("button", { name: "ออกจากระบบ" }));

    expect(await screen.findByLabelText("ชื่อผู้ใช้")).toBeInTheDocument();
    expect(location()).toBe("/login");
    expect(screen.queryByText("เซสชันหมดอายุแล้ว กรุณาเข้าสู่ระบบอีกครั้ง")).not.toBeInTheDocument();
  });

  it("shows the sign-out error and stays signed in when logout fails", async () => {
    getCurrentAdmin.mockResolvedValue(admin);
    logout.mockRejectedValue(new ApiError(0, NETWORK_ERROR_MESSAGE));
    renderAt("/volunteers");
    await userEvent.click(await screen.findByRole("button", { name: "ออกจากระบบ" }));

    expect(await screen.findByText(NETWORK_ERROR_MESSAGE)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ออกจากระบบ" })).toBeEnabled();
    expect(location()).toBe("/volunteers");
  });

  it.each([
    ["5xx", new ApiError(503, "ระบบขัดข้อง"), "ระบบขัดข้อง"],
    ["network", new ApiError(0, NETWORK_ERROR_MESSAGE), NETWORK_ERROR_MESSAGE],
  ])("shows an error screen with retry when /admin/me fails (%s)", async (_label, failure, text) => {
    getCurrentAdmin.mockRejectedValueOnce(failure).mockResolvedValueOnce(admin);
    renderAt("/volunteers");

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByLabelText("ชื่อผู้ใช้")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "ลองอีกครั้ง" }));
    expect(await screen.findByRole("heading", { name: "จิตอาสา" })).toBeInTheDocument();
    expect(getCurrentAdmin).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(location()).toBe("/volunteers"));
  });
});
