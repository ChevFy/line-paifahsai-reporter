import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { VolunteerFilters, VolunteerPage } from "../types/admin";
import { ApiError } from "../utils/api-error";
import { useVolunteerPage } from "./useVolunteerPage";

const { listVolunteers } = vi.hoisted(() => ({ listVolunteers: vi.fn() }));
vi.mock("../services/volunteer-service", () => ({ listVolunteers }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const pendingFilters: VolunteerFilters = { status: "pending", districtCode: null, limit: 50, offset: 0 };
const approvedFilters: VolunteerFilters = { ...pendingFilters, status: "approved" };

function pageOf(total: number): VolunteerPage {
  return { items: [], total, limit: 50, offset: 0 };
}

function renderVolunteerPage(initial: VolunteerFilters) {
  return renderHook((filters: VolunteerFilters) => useVolunteerPage(filters), { initialProps: initial });
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("useVolunteerPage", () => {
  it("loading → success", async () => {
    const first = deferred<VolunteerPage>();
    listVolunteers.mockReturnValueOnce(first.promise);
    const { result } = renderVolunteerPage(pendingFilters);

    expect(result.current).toMatchObject({ page: null, error: null, isLoading: true });
    await act(async () => first.resolve(pageOf(3)));
    expect(result.current).toMatchObject({ page: pageOf(3), error: null, isLoading: false });
    expect(listVolunteers).toHaveBeenCalledWith(pendingFilters);
  });

  it("loading → error with the ApiError message", async () => {
    listVolunteers.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    const { result } = renderVolunteerPage(pendingFilters);
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current).toMatchObject({ page: null, error: "ระบบขัดข้อง" });
  });

  it("a non-ApiError (e.g. JSON SyntaxError) yields the fallback message", async () => {
    listVolunteers.mockRejectedValueOnce(new SyntaxError("Unexpected token '<'"));
    const { result } = renderVolunteerPage(pendingFilters);
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe("โหลดรายชื่อจิตอาสาไม่สำเร็จ");
  });

  it("changing the filter hides the previous filter's page while the new request is in flight", async () => {
    listVolunteers.mockResolvedValueOnce(pageOf(7));
    const { result, rerender } = renderVolunteerPage(pendingFilters);
    await waitFor(() => expect(result.current.page).toEqual(pageOf(7)));

    const next = deferred<VolunteerPage>();
    listVolunteers.mockReturnValueOnce(next.promise);
    rerender(approvedFilters);
    expect(result.current).toMatchObject({ page: null, error: null, isLoading: true });

    await act(async () => next.resolve(pageOf(2)));
    expect(result.current).toMatchObject({ page: pageOf(2), isLoading: false });
  });

  it.each([
    ["status", { status: "approved" }],
    ["district", { districtCode: "5803" }],
    ["offset", { offset: 50 }],
  ] as const)("a failed request for a new %s filter shows no rows", async (_label, change) => {
    listVolunteers.mockResolvedValueOnce(pageOf(7));
    const { result, rerender } = renderVolunteerPage(pendingFilters);
    await waitFor(() => expect(result.current.page).toEqual(pageOf(7)));

    listVolunteers.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    rerender({ ...pendingFilters, ...change });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current).toMatchObject({ page: null, error: "ระบบขัดข้อง" });
  });

  it("reload keeps the current page while loading; a failed reload of the same filter keeps the rows", async () => {
    listVolunteers.mockResolvedValueOnce(pageOf(7));
    const { result } = renderVolunteerPage(pendingFilters);
    await waitFor(() => expect(result.current.page).toEqual(pageOf(7)));

    const reload = deferred<VolunteerPage>();
    listVolunteers.mockReturnValueOnce(reload.promise);
    act(() => result.current.reload());
    expect(result.current).toMatchObject({ page: pageOf(7), error: null, isLoading: true });

    await act(async () => reload.reject(new ApiError(500, "ระบบขัดข้อง")));
    expect(result.current).toMatchObject({ page: pageOf(7), error: "ระบบขัดข้อง", isLoading: false });
    expect(listVolunteers).toHaveBeenCalledTimes(2);
  });

  it("retry after an error clears the error and shows the new page", async () => {
    listVolunteers.mockRejectedValueOnce(new ApiError(0, "network")).mockResolvedValueOnce(pageOf(1));
    const { result } = renderVolunteerPage(pendingFilters);
    await waitFor(() => expect(result.current.error).toBe("network"));

    act(() => result.current.reload());
    expect(result.current).toMatchObject({ error: null, isLoading: true });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current).toMatchObject({ page: pageOf(1), error: null });
  });

  it("a stale response from the previous filter is ignored", async () => {
    const stale = deferred<VolunteerPage>();
    const fresh = deferred<VolunteerPage>();
    listVolunteers.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);
    const { result, rerender } = renderVolunteerPage(pendingFilters);
    rerender(approvedFilters);

    await act(async () => fresh.resolve(pageOf(2)));
    await act(async () => stale.resolve(pageOf(99)));
    expect(result.current).toMatchObject({ page: pageOf(2), isLoading: false });
  });
});
