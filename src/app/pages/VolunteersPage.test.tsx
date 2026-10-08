import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import type { Volunteer, VolunteerPage } from "../types/admin";
import { ApiError, NETWORK_ERROR_MESSAGE } from "../utils/api-error";
import VolunteersPage from "./VolunteersPage";

const { listVolunteers, changeVolunteerStatus } = vi.hoisted(() => ({
  listVolunteers: vi.fn(),
  changeVolunteerStatus: vi.fn(),
}));
vi.mock("../services/volunteer-service", () => ({ listVolunteers, changeVolunteerStatus }));

const { listDistricts } = vi.hoisted(() => ({ listDistricts: vi.fn() }));
vi.mock("../services/district-service", () => ({ listDistricts }));

const districts = [
  { code: "5803", name_th: "ปาย", province_name_th: "แม่ฮ่องสอน" },
  { code: "5801", name_th: "เมืองแม่ฮ่องสอน", province_name_th: "แม่ฮ่องสอน" },
];

function makeVolunteer(overrides: Partial<Volunteer> = {}): Volunteer {
  return {
    id: 1,
    full_name: "สมชาย ใจดี",
    phone: "0812345678",
    district_code: "5803",
    status: "pending",
    approved_at: null,
    created_at: "2026-10-01T03:30:00Z",
    ...overrides,
  };
}

function pageOf(items: Volunteer[], total = items.length, offset = 0): VolunteerPage {
  return { items, total, limit: 50, offset };
}

const somchai = makeVolunteer();
const somying = makeVolunteer({ id: 2, full_name: "สมหญิง รักดี", district_code: "5801" });

function LocationDisplay() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

function renderPage(path = "/volunteers") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/volunteers" element={<VolunteersPage />} />
      </Routes>
      <LocationDisplay />
    </MemoryRouter>,
  );
}

const location = () => screen.getByTestId("location").textContent;
const lastFilters = () => listVolunteers.mock.lastCall?.[0];

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  listDistricts.mockResolvedValue(districts);
  listVolunteers.mockResolvedValue(pageOf([somchai, somying]));
});

afterEach(() => {
  // Unmount before resetting mocks so no effect runs against reset (undefined) mocks
  cleanup();
  vi.resetAllMocks();
});

describe("VolunteersPage — loading and filters", () => {
  it("loads the pending tab first with limit=50 offset=0", async () => {
    renderPage();
    expect(await screen.findByText("สมชาย ใจดี")).toBeInTheDocument();

    expect(listVolunteers).toHaveBeenCalledWith({
      status: "pending",
      districtCode: null,
      limit: 50,
      offset: 0,
    });
    expect(screen.getByRole("button", { name: "รออนุมัติ" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("ทั้งหมด 2 คน")).toBeInTheDocument();
  });

  it("shows a loading status before the first page arrives", () => {
    listVolunteers.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("กำลังโหลดรายชื่อจิตอาสา...");
  });

  it("shows the district name instead of the code, and falls back to the code when unknown", async () => {
    listVolunteers.mockResolvedValue(
      pageOf([somchai, makeVolunteer({ id: 3, full_name: "ไม่รู้ อำเภอ", district_code: "9999" })]),
    );
    renderPage();
    const row = (await screen.findByText("สมชาย ใจดี")).closest("tr")!;
    await waitFor(() => expect(within(row).getByText("ปาย")).toBeInTheDocument());
    expect(within(row).queryByText("5803")).not.toBeInTheDocument();

    const unknownRow = screen.getByText("ไม่รู้ อำเภอ").closest("tr")!;
    expect(within(unknownRow).getByText("9999")).toBeInTheDocument();
  });

  it("switching the status tab requests that status and resets the page", async () => {
    renderPage("/volunteers?page=3");
    await screen.findByText("สมชาย ใจดี");
    expect(lastFilters()).toMatchObject({ status: "pending", offset: 100 });

    await userEvent.click(screen.getByRole("button", { name: "อนุมัติแล้ว" }));
    await waitFor(() => expect(lastFilters()).toEqual({ status: "approved", districtCode: null, limit: 50, offset: 0 }));
    expect(location()).toBe("/volunteers?status=approved");
    expect(screen.getByRole("button", { name: "อนุมัติแล้ว" })).toHaveAttribute("aria-pressed", "true");
  });

  it("the 'ทั้งหมด' tab sends no status filter", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "ทั้งหมด" }));
    await waitFor(() => expect(lastFilters()).toMatchObject({ status: null, offset: 0 }));
  });

  it("switching the district requests that district and resets the page", async () => {
    renderPage("/volunteers?status=approved&page=2");
    await screen.findByText("สมชาย ใจดี");
    const select = screen.getByLabelText("อำเภอ");
    await screen.findByRole("option", { name: "ปาย" });

    await userEvent.selectOptions(select, "5803");
    await waitFor(() =>
      expect(lastFilters()).toEqual({ status: "approved", districtCode: "5803", limit: 50, offset: 0 }),
    );
    expect(location()).toBe("/volunteers?status=approved&district=5803");

    await userEvent.selectOptions(select, "");
    await waitFor(() => expect(lastFilters()).toMatchObject({ districtCode: null }));
  });

  it("shows the empty state", async () => {
    listVolunteers.mockResolvedValue(pageOf([]));
    renderPage();
    expect(await screen.findByText("ไม่มีจิตอาสาในหมวดนี้")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "เลือกหน้า" })).not.toBeInTheDocument();
  });

  it("shows the list error with retry, and retry reloads", async () => {
    listVolunteers.mockRejectedValueOnce(new ApiError(0, NETWORK_ERROR_MESSAGE));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(NETWORK_ERROR_MESSAGE);

    await userEvent.click(within(alert).getByRole("button", { name: "ลองอีกครั้ง" }));
    expect(await screen.findByText("สมชาย ใจดี")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(listVolunteers).toHaveBeenCalledTimes(2);
  });

  it("keeps the rows on screen when a refresh fails", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    listVolunteers.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));

    await userEvent.click(screen.getByRole("button", { name: "โหลดใหม่" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ระบบขัดข้อง");
    expect(screen.getByText("สมชาย ใจดี")).toBeInTheDocument();
  });

  it("shows the district load error", async () => {
    listDistricts.mockRejectedValue(new ApiError(500, "โหลดรายชื่ออำเภอไม่สำเร็จ"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("โหลดรายชื่ออำเภอไม่สำเร็จ");
    expect(alert).toHaveClass("error-box");
    // The volunteer list itself still loads
    expect(await screen.findByText("สมชาย ใจดี")).toBeInTheDocument();
  });

  it("a non-ApiError from the district service shows the fallback text, not the raw message", async () => {
    listDistricts.mockRejectedValue(new SyntaxError("Unexpected token '<', \"<!doctype \"... is not valid JSON"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("โหลดรายชื่ออำเภอไม่สำเร็จ");
    expect(alert).not.toHaveTextContent("Unexpected token");
  });

  it("switching the tab hides the previous tab's rows and total while the new request is in flight", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    expect(screen.getByText("ทั้งหมด 2 คน")).toBeInTheDocument();

    const next = deferred<VolunteerPage>();
    listVolunteers.mockReturnValueOnce(next.promise);
    await userEvent.click(screen.getByRole("button", { name: "อนุมัติแล้ว" }));

    expect(screen.queryByText("สมชาย ใจดี")).not.toBeInTheDocument();
    expect(screen.queryByText("ทั้งหมด 2 คน")).not.toBeInTheDocument();
    expect(screen.getByText("กำลังโหลด...")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("กำลังโหลดรายชื่อจิตอาสา...");

    await act(async () => next.resolve(pageOf([makeVolunteer({ id: 9, full_name: "คนใหม่", status: "approved" })])));
    expect(screen.getByText("คนใหม่")).toBeInTheDocument();
    expect(screen.getByText("ทั้งหมด 1 คน")).toBeInTheDocument();
  });

  it("switching the district hides the previous rows while loading", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await screen.findByRole("option", { name: "ปาย" });

    listVolunteers.mockReturnValueOnce(new Promise(() => undefined));
    await userEvent.selectOptions(screen.getByLabelText("อำเภอ"), "5803");
    expect(screen.queryByText("สมชาย ใจดี")).not.toBeInTheDocument();
    expect(screen.queryByText("ทั้งหมด 2 คน")).not.toBeInTheDocument();
  });

  it("changing page hides the previous page's rows while loading", async () => {
    listVolunteers.mockResolvedValue(pageOf([somchai], 101));
    renderPage();
    await screen.findByText("สมชาย ใจดี");

    listVolunteers.mockReturnValueOnce(new Promise(() => undefined));
    await userEvent.click(screen.getByRole("button", { name: "ถัดไป" }));
    expect(screen.queryByText("สมชาย ใจดี")).not.toBeInTheDocument();
    expect(screen.queryByText("ทั้งหมด 101 คน")).not.toBeInTheDocument();
  });

  it("a failed request for a new filter shows no rows and no total", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");

    listVolunteers.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    await userEvent.click(screen.getByRole("button", { name: "อนุมัติแล้ว" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("ระบบขัดข้อง");
    expect(screen.queryByText("สมชาย ใจดี")).not.toBeInTheDocument();
    expect(screen.queryByText(/^ทั้งหมด \d+ คน$/)).not.toBeInTheDocument();
    expect(screen.queryByText("ไม่มีจิตอาสาในหมวดนี้")).not.toBeInTheDocument();
  });

  it("the subtitle shows 'กำลังโหลด...' only while loading and nothing after a failed first load", async () => {
    const first = deferred<VolunteerPage>();
    listVolunteers.mockReturnValueOnce(first.promise);
    renderPage();
    expect(screen.getByText("กำลังโหลด...")).toBeInTheDocument();

    await act(async () => first.reject(new ApiError(500, "ระบบขัดข้อง")));
    expect(screen.getByRole("alert")).toHaveTextContent("ระบบขัดข้อง");
    expect(screen.queryByText("กำลังโหลด...")).not.toBeInTheDocument();
    const subtitle = screen.getByRole("heading", { name: "จิตอาสา" }).nextElementSibling;
    expect(subtitle).toBeEmptyDOMElement();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("a non-ApiError on the list shows the fallback text", async () => {
    listVolunteers.mockRejectedValueOnce(new SyntaxError("Unexpected token '<'"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("โหลดรายชื่อจิตอาสาไม่สำเร็จ");
    expect(alert).not.toHaveTextContent("Unexpected token");
  });
});

describe("VolunteersPage — pagination", () => {
  it("computes ceil(total/50) pages and sends the right offset", async () => {
    listVolunteers.mockResolvedValue(pageOf([somchai], 101));
    renderPage();
    const nav = await screen.findByRole("navigation", { name: "เลือกหน้า" });
    expect(within(nav).getByText("หน้า 1 / 3")).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "ก่อนหน้า" })).toBeDisabled();

    await userEvent.click(within(nav).getByRole("button", { name: "ถัดไป" }));
    await waitFor(() => expect(lastFilters()).toMatchObject({ offset: 50 }));
    expect(location()).toBe("/volunteers?page=2");

    await userEvent.click(await screen.findByRole("button", { name: "ถัดไป" }));
    await waitFor(() => expect(lastFilters()).toMatchObject({ offset: 100 }));
    expect(await screen.findByText("หน้า 3 / 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ถัดไป" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "ก่อนหน้า" }));
    await waitFor(() => expect(lastFilters()).toMatchObject({ offset: 50 }));
  });

  it("going back to page 1 removes the page param", async () => {
    listVolunteers.mockResolvedValue(pageOf([somchai], 60));
    renderPage("/volunteers?page=2");
    await screen.findByText("หน้า 2 / 2");
    await userEvent.click(screen.getByRole("button", { name: "ก่อนหน้า" }));
    await waitFor(() => expect(location()).toBe("/volunteers"));
    expect(lastFilters()).toMatchObject({ offset: 0 });
  });

  it("exactly 50 rows is one page (no pagination)", async () => {
    listVolunteers.mockResolvedValue(pageOf([somchai], 50));
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    expect(screen.queryByRole("navigation", { name: "เลือกหน้า" })).not.toBeInTheDocument();
  });

  it.each(["0", "-1", "abc", "1.5"])("an invalid page param %j falls back to page 1", async (value) => {
    renderPage(`/volunteers?page=${value}`);
    await screen.findByText("สมชาย ใจดี");
    expect(lastFilters()).toMatchObject({ offset: 0 });
  });

  it("an invalid status param falls back to pending", async () => {
    renderPage("/volunteers?status=bogus");
    await screen.findByText("สมชาย ใจดี");
    expect(lastFilters()).toMatchObject({ status: "pending" });
  });

  it("steps back to the last page when the current page is past the end", async () => {
    listVolunteers.mockImplementation(async ({ offset }: { offset: number }) =>
      offset >= 100 ? pageOf([], 51, offset) : pageOf([somchai], 51, offset),
    );
    renderPage("/volunteers?page=3");

    await waitFor(() => expect(location()).toBe("/volunteers?page=2"));
    expect(await screen.findByText("สมชาย ใจดี")).toBeInTheDocument();
    expect(lastFilters()).toMatchObject({ offset: 50 });
    expect(screen.getByText("หน้า 2 / 2")).toBeInTheDocument();
  });

  it("after handling the last row on the last page, steps back a page", async () => {
    const lastRow = makeVolunteer({ id: 51, full_name: "คนสุดท้าย" });
    listVolunteers.mockImplementation(async ({ offset }: { offset: number }) =>
      offset === 50 ? pageOf([lastRow], 51, 50) : pageOf([somchai], 51, offset),
    );
    changeVolunteerStatus.mockResolvedValue({ ...lastRow, status: "approved" });
    renderPage("/volunteers?page=2");
    await screen.findByText("คนสุดท้าย");

    // After approval the pending list shrinks to 50 → page 2 is now empty
    listVolunteers.mockImplementation(async ({ offset }: { offset: number }) =>
      offset >= 50 ? pageOf([], 50, offset) : pageOf([somchai], 50, offset),
    );
    await userEvent.click(screen.getByRole("button", { name: "อนุมัติ คนสุดท้าย" }));

    await waitFor(() => expect(location()).toBe("/volunteers?page=1"));
    expect(await screen.findByText("สมชาย ใจดี")).toBeInTheDocument();
    expect(lastFilters()).toMatchObject({ offset: 0 });
  });
});

describe("VolunteersPage — actions", () => {
  it("shows the right actions per status", async () => {
    listVolunteers.mockResolvedValue(
      pageOf([
        makeVolunteer({ id: 1, full_name: "A", status: "pending" }),
        makeVolunteer({ id: 2, full_name: "B", status: "approved", approved_at: "2026-10-02T00:00:00Z" }),
        makeVolunteer({ id: 3, full_name: "C", status: "rejected" }),
        makeVolunteer({ id: 4, full_name: "D", status: "suspended" }),
      ]),
    );
    renderPage("/volunteers?status=all");
    await screen.findByText("A");

    expect(screen.getByRole("button", { name: "อนุมัติ A" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ไม่อนุมัติ A" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ระงับ B" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "อนุมัติ B" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "อนุมัติ C" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "อนุมัติ D" })).toBeInTheDocument();
  });

  it("approve calls the API without a dialog, reloads the current page and shows success", async () => {
    changeVolunteerStatus.mockResolvedValue({ ...somchai, status: "approved" });
    renderPage("/volunteers?page=2");
    listVolunteers.mockResolvedValue(pageOf([somchai, somying], 60, 50));
    await screen.findByText("สมชาย ใจดี");
    const callsBefore = listVolunteers.mock.calls.length;

    await userEvent.click(screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(changeVolunteerStatus).toHaveBeenCalledWith(1, "approve");
    expect(await screen.findByRole("status")).toHaveTextContent("อนุมัติ สมชาย ใจดี แล้ว");
    await waitFor(() => expect(listVolunteers.mock.calls.length).toBe(callsBefore + 1));
    expect(lastFilters()).toEqual({ status: "pending", districtCode: null, limit: 50, offset: 50 });
  });

  it.each([
    ["reject", "ไม่อนุมัติ", somchai, "pending", "สมชาย ใจดี จะไม่ได้เป็นจิตอาสาและจะได้รับแจ้งผลทาง LINE"],
    [
      "suspend",
      "ระงับ",
      makeVolunteer({ status: "approved" }),
      "approved",
      "สมชาย ใจดี จะไม่ได้รับแจ้งเหตุไฟป่าอีกจนกว่าจะอนุมัติใหม่ และจะได้รับแจ้งผลทาง LINE",
    ],
  ] as const)("%s opens the confirm dialog; cancel does nothing", async (_action, label, volunteer, tab, description) => {
    listVolunteers.mockResolvedValue(pageOf([volunteer]));
    renderPage(`/volunteers?status=${tab}`);
    await screen.findByText("สมชาย ใจดี");

    await userEvent.click(screen.getByRole("button", { name: `${label} สมชาย ใจดี` }));
    const dialog = screen.getByRole("alertdialog", { name: `${label} สมชาย ใจดี?` });
    expect(dialog).toHaveAccessibleDescription(description);
    expect(changeVolunteerStatus).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("button", { name: "ยกเลิก" })).toHaveFocus();

    await userEvent.click(within(dialog).getByRole("button", { name: "ยกเลิก" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(changeVolunteerStatus).not.toHaveBeenCalled();
  });

  it.each([
    ["reject", "ไม่อนุมัติ", "pending", "pending"],
    ["suspend", "ระงับ", "approved", "approved"],
  ] as const)("%s: confirming calls the API, closes the dialog and reloads", async (action, label, status, tab) => {
    listVolunteers.mockResolvedValue(pageOf([makeVolunteer({ status })]));
    changeVolunteerStatus.mockResolvedValue(makeVolunteer());
    renderPage(`/volunteers?status=${tab}`);
    await screen.findByText("สมชาย ใจดี");
    const callsBefore = listVolunteers.mock.calls.length;

    await userEvent.click(screen.getByRole("button", { name: `${label} สมชาย ใจดี` }));
    const dialog = screen.getByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: label }));

    expect(changeVolunteerStatus).toHaveBeenCalledWith(1, action);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(await screen.findByRole("status")).toHaveTextContent(`${label} สมชาย ใจดี แล้ว`);
    await waitFor(() => expect(listVolunteers.mock.calls.length).toBe(callsBefore + 1));
  });

  it("Escape closes the confirm dialog without calling the API", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "ไม่อนุมัติ สมชาย ใจดี" }));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(changeVolunteerStatus).not.toHaveBeenCalled();
  });

  it("while confirming is in flight the dialog is busy and Escape does not close it", async () => {
    const pending = deferred<Volunteer>();
    changeVolunteerStatus.mockReturnValue(pending.promise);
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "ไม่อนุมัติ สมชาย ใจดี" }));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "ไม่อนุมัติ" }));

    const dialog = screen.getByRole("alertdialog");
    const busyConfirm = within(dialog).getByRole("button", { name: "กำลังดำเนินการ..." });
    expect(busyConfirm).toBeDisabled();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    await act(async () => pending.resolve(makeVolunteer({ status: "rejected" })));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(changeVolunteerStatus).toHaveBeenCalledTimes(1);
  });

  it("a 404 on an action shows the backend error AND reloads the list", async () => {
    changeVolunteerStatus.mockRejectedValue(new ApiError(404, "ไม่พบจิตอาสา"));
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    const callsBefore = listVolunteers.mock.calls.length;

    await userEvent.click(screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("ไม่พบจิตอาสา");
    await waitFor(() => expect(listVolunteers.mock.calls.length).toBe(callsBefore + 1));
    expect(screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" })).toBeEnabled();
  });

  it("a network error on an action shows the network message", async () => {
    changeVolunteerStatus.mockRejectedValue(new ApiError(0, NETWORK_ERROR_MESSAGE));
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(NETWORK_ERROR_MESSAGE);
  });

  it("a 401 on an action shows no error notice (the session handler takes over)", async () => {
    changeVolunteerStatus.mockRejectedValue(new ApiError(401, "กรุณาเข้าสู่ระบบ"));
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" })).toBeEnabled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("disables every action button while one action runs and never calls the API twice", async () => {
    const pending = deferred<Volunteer>();
    changeVolunteerStatus.mockReturnValue(pending.promise);
    renderPage();
    await screen.findByText("สมชาย ใจดี");

    const approve = screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" });
    await userEvent.click(approve);
    await userEvent.click(approve);
    await userEvent.click(screen.getByRole("button", { name: "อนุมัติ สมหญิง รักดี" }));

    for (const button of screen.getAllByRole("button", { name: /^(อนุมัติ|ไม่อนุมัติ) / })) {
      expect(button).toBeDisabled();
    }
    expect(changeVolunteerStatus).toHaveBeenCalledTimes(1);

    await act(async () => pending.resolve({ ...somchai, status: "approved" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "อนุมัติ สมหญิง รักดี" })).toBeEnabled());
  });

  it("double-clicking confirm in the dialog only calls the API once", async () => {
    const pending = deferred<Volunteer>();
    changeVolunteerStatus.mockReturnValue(pending.promise);
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "ไม่อนุมัติ สมชาย ใจดี" }));
    const confirm = within(screen.getByRole("alertdialog")).getByRole("button", { name: "ไม่อนุมัติ" });

    await userEvent.dblClick(confirm);
    expect(changeVolunteerStatus).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve(makeVolunteer({ status: "rejected" })));
  });

  it("two confirm clicks inside the same act (before re-render) call the API only once", async () => {
    const pending = deferred<Volunteer>();
    changeVolunteerStatus.mockReturnValue(pending.promise);
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "ไม่อนุมัติ สมชาย ใจดี" }));
    const confirm = within(screen.getByRole("alertdialog")).getByRole("button", { name: "ไม่อนุมัติ" });

    act(() => {
      // No re-render happens between these clicks, so `disabled` cannot stop the second one
      confirm.click();
      confirm.click();
    });
    expect(changeVolunteerStatus).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve(makeVolunteer({ status: "rejected" })));
  });

  it("row action buttons are disabled while the confirm dialog is open", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "ไม่อนุมัติ สมชาย ใจดี" }));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    for (const name of ["อนุมัติ สมหญิง รักดี", "ไม่อนุมัติ สมหญิง รักดี", "อนุมัติ สมชาย ใจดี"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    // A keyboard user activating another row behind the dialog does nothing
    screen.getByRole("button", { name: "อนุมัติ สมหญิง รักดี" }).click();
    expect(changeVolunteerStatus).not.toHaveBeenCalled();

    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "ยกเลิก" }));
    expect(screen.getByRole("button", { name: "อนุมัติ สมหญิง รักดี" })).toBeEnabled();
  });

  it("row action buttons are disabled while the list is reloading", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");

    const reload = deferred<VolunteerPage>();
    listVolunteers.mockReturnValueOnce(reload.promise);
    await userEvent.click(screen.getByRole("button", { name: "โหลดใหม่" }));

    // Same filter: rows stay visible, but cannot be acted on with possibly stale data
    const approve = screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" });
    expect(approve).toBeDisabled();
    approve.click();
    expect(changeVolunteerStatus).not.toHaveBeenCalled();

    await act(async () => reload.resolve(pageOf([somchai, somying])));
    expect(screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" })).toBeEnabled();
  });

  it("action buttons are wrapped in a .row-actions container inside the cell", async () => {
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    const approve = screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" });
    const wrapper = approve.parentElement!;
    expect(wrapper).toHaveClass("row-actions");
    expect(wrapper.parentElement!.tagName).toBe("TD");
    expect(within(wrapper).getByRole("button", { name: "ไม่อนุมัติ สมชาย ใจดี" })).toBeInTheDocument();
  });

  it("a non-ApiError on an action shows the fallback text", async () => {
    changeVolunteerStatus.mockRejectedValue(new SyntaxError("Unexpected token '<'"));
    renderPage();
    await screen.findByText("สมชาย ใจดี");
    await userEvent.click(screen.getByRole("button", { name: "อนุมัติ สมชาย ใจดี" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("เปลี่ยนสถานะจิตอาสาไม่สำเร็จ");
    expect(alert).not.toHaveTextContent("Unexpected token");
  });
});
