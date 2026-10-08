import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import type { ActiveIncident, ActiveIncidentList } from "../types/admin";
import { ApiError, NETWORK_ERROR_MESSAGE } from "../utils/api-error";
import { INCIDENT_STATUS_LABELS } from "../utils/incident-labels";
import IncidentsMapPage from "./IncidentsMapPage";

const { listActiveIncidents } = vi.hoisted(() => ({ listActiveIncidents: vi.fn() }));
vi.mock("../services/incident-service", () => ({ listActiveIncidents }));

const { listDistricts } = vi.hoisted(() => ({ listDistricts: vi.fn() }));
vi.mock("../services/district-service", () => ({ listDistricts }));

// Leaflet needs real layout; a stub that exposes the props the page passes is enough here
vi.mock("../components/IncidentMap", () => ({
  default: ({
    incidents,
    fitKey,
    selectedId,
    onSelect,
  }: {
    incidents: ActiveIncident[];
    fitKey: string;
    selectedId: number | null;
    onSelect: (id: number) => void;
  }) => (
    <div data-testid="map" data-fit-key={fitKey} data-selected={selectedId ?? ""}>
      {incidents.map((incident) => (
        <button key={incident.id} type="button" onClick={() => onSelect(incident.id)}>
          pin {incident.id}
        </button>
      ))}
    </div>
  ),
}));

const districts = [
  { code: "5803", name_th: "ปาย", province_name_th: "แม่ฮ่องสอน" },
  { code: "5801", name_th: "เมืองแม่ฮ่องสอน", province_name_th: "แม่ฮ่องสอน" },
];

function makeIncident(overrides: Partial<ActiveIncident> = {}): ActiveIncident {
  return {
    id: 1,
    latitude: 19.3581234,
    longitude: 98.4371,
    district_code: "5803",
    status: "open",
    report_count: 2,
    created_at: "2026-10-09T02:30:00Z",
    ...overrides,
  };
}

// 03:00 UTC = 10:00 in Bangkok; deliberately far from the real clock so the
// elapsed-time text proves it is computed against generated_at, not Date.now()
const GENERATED_AT = "2026-10-09T03:00:00Z";

function listOf(incidents: ActiveIncident[], extra: Partial<ActiveIncidentList> = {}): ActiveIncidentList {
  return { generated_at: GENERATED_AT, incidents, truncated: false, emergency_phone: "1669", ...extra };
}

const progressOld = makeIncident({ id: 11, status: "in_progress", created_at: "2026-10-09T01:00:00Z" });
const openOld = makeIncident({ id: 12, status: "open", created_at: "2026-10-09T01:30:00Z", district_code: "5801" });
const progressNew = makeIncident({ id: 13, status: "in_progress", created_at: "2026-10-09T02:50:00Z" });
const openNew = makeIncident({ id: 14, status: "open", created_at: "2026-10-09T02:30:00Z" });
// In backend order (newest first): progress-new, open-new, open-old, progress-old
const mixed = listOf([progressNew, openNew, openOld, progressOld]);
const anySignal = expect.any(AbortSignal);

function LocationDisplay() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

function renderPage(path = "/map") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/map" element={<IncidentsMapPage />} />
      </Routes>
      <LocationDisplay />
    </MemoryRouter>,
  );
}

const location = () => screen.getByTestId("location").textContent;
const itemButton = (id: number) => screen.getByRole("button", { name: new RegExp(`^เหตุ #${id}\\b`) });
const listedIds = () =>
  screen
    .getAllByRole("button", { name: /^เหตุ #\d+/ })
    .map((button) => Number(/#(\d+)/.exec(button.textContent ?? "")![1]));
const pinIds = () =>
  within(screen.getByTestId("map"))
    .queryAllByRole("button")
    .map((button) => Number(button.textContent!.replace("pin ", "")));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

let scrollIntoView: ReturnType<typeof vi.fn>;

beforeEach(() => {
  // jsdom has no scrollIntoView
  scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView as unknown as Element["scrollIntoView"];
  listDistricts.mockResolvedValue(districts);
  listActiveIncidents.mockResolvedValue(mixed);
});

afterEach(() => {
  // Unmount before resetting mocks so no effect runs against reset (undefined) mocks
  cleanup();
  vi.useRealTimers();
  vi.resetAllMocks();
  delete (Element.prototype as Partial<Element>).scrollIntoView;
});

describe("IncidentsMapPage — loading and content", () => {
  it("shows the loading status, subtitle and a disabled reload button before the first response", () => {
    listActiveIncidents.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole("heading", { name: "เหตุที่กำลังเกิด" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("กำลังโหลดเหตุที่กำลังเกิด...");
    expect(screen.getByText("กำลังโหลด...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "โหลดใหม่" })).toBeDisabled();
    // Before data arrives the default emergency number is shown
    expect(screen.getByText("1362")).toBeInTheDocument();
  });

  it("loads all districts by default and shows counts, last update time and the emergency phone", async () => {
    renderPage();
    expect(await screen.findByText("4 เหตุ · ยังไม่มีคนรับ 2 เหตุ · อัปเดตล่าสุด 10:00 น.")).toBeInTheDocument();
    expect(listActiveIncidents).toHaveBeenCalledWith(null, anySignal);
    expect(screen.getByText("1669")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "โหลดใหม่" })).toBeEnabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("moves open before in_progress and keeps the backend (newest-first) order within each status", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    expect(listedIds()).toEqual([14, 12, 13, 11]);
    expect(pinIds()).toEqual([14, 12, 13, 11]);
  });

  it("the sort is stable: it never re-orders by created_at or id within a status", async () => {
    // Deliberately not in created_at or id order, to prove the page keeps whatever order the backend sent
    const openA = makeIncident({ id: 31, status: "open", created_at: "2026-10-09T01:00:00Z" });
    const openB = makeIncident({ id: 22, status: "open", created_at: "2026-10-09T02:00:00Z" });
    const openC = makeIncident({ id: 27, status: "open", created_at: "2026-10-09T01:30:00Z" });
    const progA = makeIncident({ id: 5, status: "in_progress", created_at: "2026-10-09T00:10:00Z" });
    const progB = makeIncident({ id: 40, status: "in_progress", created_at: "2026-10-09T02:40:00Z" });
    listActiveIncidents.mockResolvedValue(listOf([progA, openA, progB, openB, openC]));
    renderPage();
    await screen.findByText(/^5 เหตุ/);
    expect(listedIds()).toEqual([31, 22, 27, 5, 40]);
    expect(pinIds()).toEqual([31, 22, 27, 5, 40]);
  });

  it("a list with a single status keeps the backend order exactly", async () => {
    listActiveIncidents.mockResolvedValue(listOf([progressNew, progressOld]));
    renderPage();
    await screen.findByText(/^2 เหตุ/);
    expect(listedIds()).toEqual([13, 11]);
  });

  it("shows the status label, district name, report count and elapsed time per item", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    await screen.findByRole("option", { name: "ปาย" });

    const item = itemButton(14);
    expect(within(item).getByText(INCIDENT_STATUS_LABELS.open)).toHaveClass("status-badge", "status-open");
    expect(item).toHaveTextContent("อ.ปาย · แจ้ง 2 ครั้ง");
    expect(item).not.toHaveTextContent("5803");
    // 02:30 vs generated_at 03:00 → 30 minutes, regardless of the real clock
    expect(item).toHaveTextContent("30 นาทีที่ผ่านมา");

    expect(itemButton(12)).toHaveTextContent("อ.เมืองแม่ฮ่องสอน");
    expect(itemButton(11)).toHaveTextContent("2 ชั่วโมงที่ผ่านมา");
    expect(within(itemButton(13)).getByText(INCIDENT_STATUS_LABELS.in_progress)).toHaveClass("status-in_progress");
  });

  it("falls back to the district code when the name is unknown or districts fail to load", async () => {
    listDistricts.mockRejectedValue(new ApiError(500, "โหลดรายชื่ออำเภอไม่สำเร็จ"));
    listActiveIncidents.mockResolvedValue(listOf([makeIncident({ district_code: "9999" })]));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("โหลดรายชื่ออำเภอไม่สำเร็จ");
    expect(await screen.findByText(/อ\.9999 · แจ้ง 2 ครั้ง/)).toBeInTheDocument();
  });

  it("each item has a Google Maps link with 6-decimal coordinates opening in a new tab", async () => {
    listActiveIncidents.mockResolvedValue(listOf([makeIncident({ id: 5 })]));
    renderPage();
    const link = await screen.findByRole("link", { name: "เปิดเหตุ #5 ใน Google Maps" });
    expect(link).toHaveAttribute("href", "https://www.google.com/maps/search/?api=1&query=19.358123,98.437100");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
  });

  it("shows the empty state when there are no active incidents", async () => {
    listActiveIncidents.mockResolvedValue(listOf([]));
    renderPage();
    expect(await screen.findByText("ไม่มีเหตุที่กำลังเกิดอยู่ตอนนี้")).toBeInTheDocument();
    expect(screen.getByText("0 เหตุ · ยังไม่มีคนรับ 0 เหตุ · อัปเดตล่าสุด 10:00 น.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the truncated notice only when the backend truncated the list", async () => {
    listActiveIncidents.mockResolvedValue(listOf([openNew, progressNew], { truncated: true }));
    renderPage();
    await screen.findByText(/^2 เหตุ/);
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("มีเหตุมากเกินกว่าจะแสดงทั้งหมด แสดงเฉพาะ 2 เหตุล่าสุด กรองตามอำเภอเพื่อดูให้ครบ");
    expect(notice).toHaveClass("notice-box");
  });

  it("does not show the truncated notice for a complete list", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    expect(screen.queryByText(/มีเหตุมากเกินกว่าจะแสดงทั้งหมด/)).not.toBeInTheDocument();
  });
});

describe("IncidentsMapPage — reload button and time", () => {
  it("the reload button icon does not spin while loading", () => {
    listActiveIncidents.mockReturnValue(new Promise(() => undefined));
    renderPage();
    const button = screen.getByRole("button", { name: "โหลดใหม่" });
    expect(button).toBeDisabled();
    const icon = button.querySelector("svg");
    expect(icon).not.toBeNull();
    expect(icon).not.toHaveClass("spin");
  });

  it("the subtitle shows generated_at as HH:MM Bangkok time", async () => {
    listActiveIncidents.mockResolvedValue(listOf([], { generated_at: "2026-10-09T17:05:00Z" }));
    renderPage();
    expect(await screen.findByText("0 เหตุ · ยังไม่มีคนรับ 0 เหตุ · อัปเดตล่าสุด 00:05 น.")).toBeInTheDocument();
  });

  it("elapsed time follows the server clock and keeps advancing each minute even when refreshes fail", async () => {
    // waitFor/findBy poll with setInterval, which is faked here, so settle with act instead
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    // Client clock far from generated_at: the text must not depend on it
    vi.setSystemTime(new Date("2026-10-10T08:00:00Z"));
    listActiveIncidents.mockResolvedValueOnce(listOf([openNew]));
    renderPage();
    await act(async () => undefined);
    expect(itemButton(14)).toHaveTextContent("30 นาทีที่ผ่านมา");

    listActiveIncidents.mockRejectedValue(new ApiError(0, NETWORK_ERROR_MESSAGE));
    await act(async () => vi.advanceTimersByTime(60_000));
    expect(screen.getByRole("alert")).toHaveTextContent(NETWORK_ERROR_MESSAGE);
    expect(itemButton(14)).toHaveTextContent("31 นาทีที่ผ่านมา");

    await act(async () => vi.advanceTimersByTime(29 * 60_000));
    expect(itemButton(14)).toHaveTextContent("1 ชั่วโมงที่ผ่านมา");
  });
});

describe("IncidentsMapPage — errors", () => {
  it("first-load error: shows the message (without the stale note) and retry reloads", async () => {
    listActiveIncidents.mockRejectedValueOnce(new ApiError(0, NETWORK_ERROR_MESSAGE));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(NETWORK_ERROR_MESSAGE);
    expect(alert).not.toHaveTextContent("ข้อมูลบนแผนที่อาจไม่เป็นปัจจุบัน");
    expect(screen.queryByText("ไม่มีเหตุที่กำลังเกิดอยู่ตอนนี้")).not.toBeInTheDocument();
    expect(screen.queryByText("กำลังโหลด...")).not.toBeInTheDocument();

    await userEvent.click(within(alert).getByRole("button", { name: "ลองอีกครั้ง" }));
    expect(await screen.findByText(/^4 เหตุ/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(listActiveIncidents).toHaveBeenCalledTimes(2);
  });

  it("a failed refresh keeps the incidents and flags the map as possibly stale", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);

    listActiveIncidents.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    await userEvent.click(screen.getByRole("button", { name: "โหลดใหม่" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("ระบบขัดข้อง · ข้อมูลบนแผนที่อาจไม่เป็นปัจจุบัน");
    expect(listedIds()).toEqual([14, 12, 13, 11]);
    expect(pinIds()).toEqual([14, 12, 13, 11]);
  });

  it("the error stays visible while the retry is in flight and clears only when it succeeds", async () => {
    listActiveIncidents.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    renderPage();
    const alert = await screen.findByRole("alert");

    const retry = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(retry.promise);
    await userEvent.click(within(alert).getByRole("button", { name: "ลองอีกครั้ง" }));
    expect(screen.getByRole("alert")).toHaveTextContent("ระบบขัดข้อง");
    expect(screen.getByRole("button", { name: "โหลดใหม่" })).toBeDisabled();

    await act(async () => retry.resolve(mixed));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(listedIds()).toEqual([14, 12, 13, 11]);
  });

  it("switching district hides the previous district's error", async () => {
    listActiveIncidents.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    renderPage();
    await screen.findByRole("alert");
    await screen.findByRole("option", { name: "ปาย" });

    listActiveIncidents.mockReturnValueOnce(new Promise(() => undefined));
    await userEvent.selectOptions(screen.getByLabelText("อำเภอ"), "5801");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("กำลังโหลด...")).toBeInTheDocument();
  });

  it("a non-ApiError shows the fallback text, not the raw message", async () => {
    listActiveIncidents.mockRejectedValueOnce(new SyntaxError("Unexpected token '<'"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("โหลดเหตุที่กำลังเกิดไม่สำเร็จ");
    expect(alert).not.toHaveTextContent("Unexpected token");
  });

  it("the district load error does not block the incident list", async () => {
    listDistricts.mockRejectedValue(new SyntaxError("Unexpected token '<'"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("โหลดรายชื่ออำเภอไม่สำเร็จ");
    expect(alert).not.toHaveTextContent("Unexpected token");
    expect(await screen.findByText(/^4 เหตุ/)).toBeInTheDocument();
  });
});

describe("IncidentsMapPage — district filter", () => {
  it("reads ?district= from the URL", async () => {
    renderPage("/map?district=5803");
    await screen.findByText(/^4 เหตุ/);
    expect(listActiveIncidents).toHaveBeenCalledWith("5803", anySignal);
    await screen.findByRole("option", { name: "ปาย" });
    expect(screen.getByLabelText("อำเภอ")).toHaveValue("5803");
  });

  it("an empty ?district= means all districts", async () => {
    renderPage("/map?district=");
    await screen.findByText(/^4 เหตุ/);
    expect(listActiveIncidents).toHaveBeenCalledWith(null, anySignal);
  });

  it("selecting a district writes it to the URL and requests it; 'ทุกอำเภอ' removes it", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    await screen.findByRole("option", { name: "ปาย" });

    await userEvent.selectOptions(screen.getByLabelText("อำเภอ"), "5803");
    await waitFor(() => expect(listActiveIncidents).toHaveBeenLastCalledWith("5803", anySignal));
    expect(location()).toBe("/map?district=5803");

    await userEvent.selectOptions(screen.getByLabelText("อำเภอ"), "ทุกอำเภอ");
    await waitFor(() => expect(listActiveIncidents).toHaveBeenLastCalledWith(null, anySignal));
    expect(location()).toBe("/map");
  });

  it("switching district hides the previous district's incidents while loading", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    await screen.findByRole("option", { name: "ปาย" });

    const next = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(next.promise);
    await userEvent.selectOptions(screen.getByLabelText("อำเภอ"), "5801");

    expect(screen.queryByRole("button", { name: /^เหตุ #/ })).not.toBeInTheDocument();
    expect(pinIds()).toEqual([]);
    expect(screen.queryByText(/^4 เหตุ/)).not.toBeInTheDocument();
    expect(screen.getByText("กำลังโหลด...")).toBeInTheDocument();

    await act(async () => next.resolve(listOf([openOld])));
    expect(listedIds()).toEqual([12]);
  });

  it("a failed request for a new district shows no pins and no stale note", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    await screen.findByRole("option", { name: "ปาย" });

    listActiveIncidents.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    await userEvent.selectOptions(screen.getByLabelText("อำเภอ"), "5801");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("ระบบขัดข้อง");
    expect(alert).not.toHaveTextContent("ข้อมูลบนแผนที่อาจไม่เป็นปัจจุบัน");
    expect(pinIds()).toEqual([]);
    expect(screen.queryByText("ไม่มีเหตุที่กำลังเกิดอยู่ตอนนี้")).not.toBeInTheDocument();
  });
});

describe("IncidentsMapPage — selection", () => {
  it("clicking a list item selects it (aria-pressed) and passes selectedId to the map", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    expect(screen.getByTestId("map")).toHaveAttribute("data-selected", "");
    for (const id of [14, 12, 13, 11]) expect(itemButton(id)).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(itemButton(13));
    expect(itemButton(13)).toHaveAttribute("aria-pressed", "true");
    expect(itemButton(13)).toHaveClass("selected");
    expect(itemButton(14)).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("map")).toHaveAttribute("data-selected", "13");

    await userEvent.click(itemButton(14));
    expect(itemButton(13)).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("map")).toHaveAttribute("data-selected", "14");
  });

  it("clicking a pin on the map selects the matching list item", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    await userEvent.click(screen.getByRole("button", { name: "pin 12" }));
    expect(itemButton(12)).toHaveAttribute("aria-pressed", "true");
  });

  it("the selection survives a refresh of the same district", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    await userEvent.click(itemButton(12));

    await userEvent.click(screen.getByRole("button", { name: "โหลดใหม่" }));
    await waitFor(() => expect(listActiveIncidents).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole("button", { name: "โหลดใหม่" })).toBeEnabled());
    expect(itemButton(12)).toHaveAttribute("aria-pressed", "true");
  });

  it("selecting via a map pin scrolls the matching list item into view", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    expect(scrollIntoView).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "pin 11" }));
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
    const target = scrollIntoView.mock.contexts[0] as HTMLElement;
    expect(target.tagName).toBe("LI");
    expect(target.id).toBe("incident-11");
    expect(target).toContainElement(itemButton(11));
  });

  it("does not scroll again on a refresh with the same selection", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    await userEvent.click(itemButton(12));
    expect(scrollIntoView).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "โหลดใหม่" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "โหลดใหม่" })).toBeEnabled());
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("passes fitKey = district code, or 'all' for all districts", async () => {
    renderPage("/map?district=5803");
    await screen.findByText(/^4 เหตุ/);
    await screen.findByRole("option", { name: "ปาย" });
    expect(screen.getByTestId("map")).toHaveAttribute("data-fit-key", "5803");

    await userEvent.selectOptions(screen.getByLabelText("อำเภอ"), "ทุกอำเภอ");
    expect(screen.getByTestId("map")).toHaveAttribute("data-fit-key", "all");
  });

  it("changing the district clears the selection", async () => {
    renderPage();
    await screen.findByText(/^4 เหตุ/);
    await screen.findByRole("option", { name: "ปาย" });
    await userEvent.click(itemButton(14));
    expect(screen.getByTestId("map")).toHaveAttribute("data-selected", "14");

    await userEvent.selectOptions(screen.getByLabelText("อำเภอ"), "5803");
    await waitFor(() => expect(listActiveIncidents).toHaveBeenLastCalledWith("5803", anySignal));
    expect(screen.getByTestId("map")).toHaveAttribute("data-selected", "");
    await screen.findByText(/^4 เหตุ/);
    expect(itemButton(14)).toHaveAttribute("aria-pressed", "false");
  });
});
