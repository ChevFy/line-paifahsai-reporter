import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ActiveIncident, ActiveIncidentList } from "../types/admin";
import { ApiError, NETWORK_ERROR_MESSAGE } from "../utils/api-error";
import { REFRESH_INTERVAL_MS, REQUEST_TIMEOUT_MS, useActiveIncidents } from "./useActiveIncidents";

const { listActiveIncidents } = vi.hoisted(() => ({ listActiveIncidents: vi.fn() }));
vi.mock("../services/incident-service", () => ({ listActiveIncidents }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// waitFor polls with setInterval, which is faked here, so settle resolved mocks with act instead
const flush = () => act(async () => undefined);

function incident(id: number, district_code = "5803"): ActiveIncident {
  return {
    id,
    latitude: 19.36,
    longitude: 98.44,
    district_code,
    status: "open",
    report_count: 1,
    created_at: "2026-10-09T02:00:00Z",
  };
}

function listOf(incidents: ActiveIncident[], generated_at = "2026-10-09T03:00:00Z"): ActiveIncidentList {
  return { generated_at, incidents, truncated: false, emergency_phone: "1362" };
}

const paiList = listOf([incident(1)]);
const muangList = listOf([incident(2, "5801")]);

function renderIncidents(initial: string | null) {
  return renderHook((districtCode: string | null) => useActiveIncidents(districtCode), {
    initialProps: initial,
  });
}

// The client clock is deliberately far from generated_at so serverNow provably uses the server time
const CLIENT_NOW = new Date("2026-10-09T09:00:00Z");
const anySignal = expect.any(AbortSignal);

beforeEach(() => {
  // Only the polling interval and Date are faked; setTimeout and promises keep running normally
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
  vi.setSystemTime(CLIENT_NOW);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.resetAllMocks();
});

describe("useActiveIncidents — single request", () => {
  it("polls every 60 seconds", () => {
    expect(REFRESH_INTERVAL_MS).toBe(60_000);
  });

  it("loading → success", async () => {
    const first = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(first.promise);
    const { result } = renderIncidents(null);

    expect(result.current).toMatchObject({ data: null, error: null, isLoading: true });
    await act(async () => first.resolve(paiList));
    expect(result.current).toMatchObject({ data: paiList, error: null, isLoading: false });
    expect(listActiveIncidents).toHaveBeenCalledWith(null, anySignal);
  });

  it("passes the district code to the service", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result } = renderIncidents("5803");
    await flush();
    expect(result.current.isLoading).toBe(false);
    expect(listActiveIncidents).toHaveBeenCalledWith("5803", anySignal);
  });

  it("loading → empty (an empty list is data, not an error)", async () => {
    listActiveIncidents.mockResolvedValueOnce(listOf([]));
    const { result } = renderIncidents(null);
    await flush();
    expect(result.current.isLoading).toBe(false);
    expect(result.current).toMatchObject({ data: listOf([]), error: null });
  });

  it("loading → error with the ApiError message", async () => {
    listActiveIncidents.mockRejectedValueOnce(new ApiError(0, NETWORK_ERROR_MESSAGE));
    const { result } = renderIncidents(null);
    await flush();
    expect(result.current.isLoading).toBe(false);
    expect(result.current).toMatchObject({ data: null, error: NETWORK_ERROR_MESSAGE });
  });

  it("a non-ApiError yields the fallback message", async () => {
    listActiveIncidents.mockRejectedValueOnce(new SyntaxError("Unexpected token '<'"));
    const { result } = renderIncidents(null);
    await flush();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBe("โหลดเหตุที่กำลังเกิดไม่สำเร็จ");
  });

  it("retry after an error keeps the error visible while in flight, then clears it on success", async () => {
    const retry = deferred<ActiveIncidentList>();
    listActiveIncidents.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง")).mockReturnValueOnce(retry.promise);
    const { result } = renderIncidents(null);
    await flush();
    expect(result.current.error).toBe("ระบบขัดข้อง");

    act(() => result.current.reload());
    expect(result.current).toMatchObject({ data: null, error: "ระบบขัดข้อง", isLoading: true });
    await act(async () => retry.resolve(paiList));
    expect(result.current.isLoading).toBe(false);
    expect(result.current).toMatchObject({ data: paiList, error: null });
    expect(listActiveIncidents).toHaveBeenCalledTimes(2);
  });

  it("reload keeps the data while loading; a failed reload of the same district keeps the data", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result } = renderIncidents("5803");
    await flush();
    expect(result.current.data).toEqual(paiList);

    const reload = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(reload.promise);
    act(() => result.current.reload());
    expect(result.current).toMatchObject({ data: paiList, error: null, isLoading: true });

    await act(async () => reload.reject(new ApiError(500, "ระบบขัดข้อง")));
    expect(result.current).toMatchObject({ data: paiList, error: "ระบบขัดข้อง", isLoading: false });
  });
});

describe("useActiveIncidents — district change", () => {
  it("never shows the previous district's data while the new request is in flight", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result, rerender } = renderIncidents("5803");
    await flush();
    expect(result.current.data).toEqual(paiList);

    const next = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(next.promise);
    rerender("5801");
    expect(result.current).toMatchObject({ data: null, error: null, isLoading: true });

    await act(async () => next.resolve(muangList));
    expect(result.current).toMatchObject({ data: muangList, isLoading: false });
    expect(listActiveIncidents).toHaveBeenLastCalledWith("5801", anySignal);
  });

  it("a failed request for a new district shows no data (not the old district's pins)", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result, rerender } = renderIncidents("5803");
    await flush();
    expect(result.current.data).toEqual(paiList);

    listActiveIncidents.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    rerender("5801");
    await flush();
    expect(result.current.isLoading).toBe(false);
    expect(result.current).toMatchObject({ data: null, error: "ระบบขัดข้อง" });
  });

  it("switching from a district to all districts also hides the old data", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result, rerender } = renderIncidents("5803");
    await flush();
    expect(result.current.data).toEqual(paiList);

    listActiveIncidents.mockRejectedValueOnce(new ApiError(0, NETWORK_ERROR_MESSAGE));
    rerender(null);
    expect(result.current.data).toBeNull();
    await flush();
    expect(result.current.isLoading).toBe(false);
    expect(result.current).toMatchObject({ data: null, error: NETWORK_ERROR_MESSAGE });
  });

  it("a late response from the previous district is ignored", async () => {
    const stale = deferred<ActiveIncidentList>();
    const fresh = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);
    const { result, rerender } = renderIncidents("5803");
    rerender("5801");

    await act(async () => fresh.resolve(muangList));
    await act(async () => stale.resolve(paiList));
    expect(result.current).toMatchObject({ data: muangList, isLoading: false });
  });

  it("a late failure from the previous district does not set an error", async () => {
    const stale = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(stale.promise).mockResolvedValueOnce(muangList);
    const { result, rerender } = renderIncidents("5803");
    rerender("5801");
    await flush();
    expect(result.current.data).toEqual(muangList);

    await act(async () => stale.reject(new ApiError(500, "ระบบขัดข้อง")));
    expect(result.current).toMatchObject({ data: muangList, error: null, isLoading: false });
  });
});

describe("useActiveIncidents — polling", () => {
  it("re-requests the same district every REFRESH_INTERVAL_MS and keeps the data meanwhile", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result } = renderIncidents("5803");
    await flush();
    expect(result.current.data).toEqual(paiList);
    expect(listActiveIncidents).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS - 1));
    expect(listActiveIncidents).toHaveBeenCalledTimes(1);

    const poll = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(poll.promise);
    act(() => vi.advanceTimersByTime(1));
    expect(listActiveIncidents).toHaveBeenCalledTimes(2);
    expect(listActiveIncidents).toHaveBeenLastCalledWith("5803", anySignal);
    expect(result.current).toMatchObject({ data: paiList, isLoading: true });

    const updated = listOf([incident(1), incident(3)], "2026-10-09T03:01:00Z");
    await act(async () => poll.resolve(updated));
    expect(result.current).toMatchObject({ data: updated, error: null, isLoading: false });

    listActiveIncidents.mockResolvedValueOnce(updated);
    act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
    expect(listActiveIncidents).toHaveBeenCalledTimes(3);
  });

  it("a failed poll keeps the last data and reports the error; the next poll clears it", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result } = renderIncidents(null);
    await flush();
    expect(result.current.data).toEqual(paiList);

    listActiveIncidents.mockRejectedValueOnce(new ApiError(0, NETWORK_ERROR_MESSAGE));
    act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
    await flush();
    expect(result.current.isLoading).toBe(false);
    expect(result.current).toMatchObject({ data: paiList, error: NETWORK_ERROR_MESSAGE });

    listActiveIncidents.mockResolvedValueOnce(paiList);
    act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
    await flush();
    expect(result.current.error).toBeNull();
    expect(result.current).toMatchObject({ data: paiList, isLoading: false });
  });

  it("polls the current district after a district change", async () => {
    listActiveIncidents.mockResolvedValue(paiList);
    const { result, rerender } = renderIncidents("5803");
    await flush();
    expect(result.current.isLoading).toBe(false);

    listActiveIncidents.mockResolvedValue(muangList);
    rerender("5801");
    await flush();
    expect(result.current.data).toEqual(muangList);
    listActiveIncidents.mockClear();

    act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
    expect(listActiveIncidents).toHaveBeenCalledTimes(1);
    expect(listActiveIncidents).toHaveBeenCalledWith("5801", anySignal);
  });

  it("clears the interval on unmount and stops polling", async () => {
    const clearSpy = vi.spyOn(window, "clearInterval");
    listActiveIncidents.mockResolvedValue(paiList);
    const { result, unmount } = renderIncidents(null);
    await flush();
    expect(result.current.isLoading).toBe(false);
    expect(vi.getTimerCount()).toBe(1);

    unmount();
    expect(clearSpy).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);

    listActiveIncidents.mockClear();
    vi.advanceTimersByTime(REFRESH_INTERVAL_MS * 3);
    expect(listActiveIncidents).not.toHaveBeenCalled();
  });

  it("a response arriving after unmount is ignored without errors", async () => {
    const pending = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(pending.promise);
    const errorSpy = vi.spyOn(console, "error");
    const { unmount } = renderIncidents(null);
    unmount();
    await act(async () => pending.resolve(paiList));
    expect(errorSpy).not.toHaveBeenCalled();
  });
});

describe("useActiveIncidents — error visibility", () => {
  it("a failed poll's error stays visible while the next poll is in flight, and a second failure keeps it", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList).mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    const { result } = renderIncidents("5803");
    await flush();
    act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
    await flush();
    expect(result.current).toMatchObject({ data: paiList, error: "ระบบขัดข้อง", isLoading: false });

    const poll = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(poll.promise);
    act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
    expect(result.current).toMatchObject({ data: paiList, error: "ระบบขัดข้อง", isLoading: true });

    await act(async () => poll.reject(new ApiError(0, NETWORK_ERROR_MESSAGE)));
    expect(result.current).toMatchObject({ data: paiList, error: NETWORK_ERROR_MESSAGE, isLoading: false });

    listActiveIncidents.mockResolvedValueOnce(paiList);
    act(() => result.current.reload());
    expect(result.current.error).toBe(NETWORK_ERROR_MESSAGE);
    await flush();
    expect(result.current).toMatchObject({ data: paiList, error: null, isLoading: false });
  });

  it("switching district clears the previous district's error immediately", async () => {
    listActiveIncidents.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    const { result, rerender } = renderIncidents("5803");
    await flush();
    expect(result.current.error).toBe("ระบบขัดข้อง");

    const next = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(next.promise);
    rerender("5801");
    expect(result.current).toMatchObject({ data: null, error: null, isLoading: true });

    await act(async () => next.resolve(muangList));
    expect(result.current).toMatchObject({ data: muangList, error: null, isLoading: false });
  });
});

describe("useActiveIncidents — request timeout", () => {
  // Node's AbortSignal.timeout runs on internal timers that vi fake timers cannot reach,
  // so it is replaced with an equivalent driven by the (faked) global setTimeout
  function fakeAbortSignalTimeout() {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout", "Date"] });
    vi.setSystemTime(CLIENT_NOW);
    return vi.spyOn(AbortSignal, "timeout").mockImplementation((ms: number) => {
      const controller = new AbortController();
      setTimeout(() => controller.abort(new DOMException("The operation timed out.", "TimeoutError")), ms);
      return controller.signal;
    });
  }

  // Behaves like the real service: a hung fetch rejects with a network ApiError once its signal aborts
  function hangUntilAborted(_districtCode: string | null, signal: AbortSignal) {
    return new Promise<ActiveIncidentList>((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new ApiError(0, NETWORK_ERROR_MESSAGE)));
    });
  }

  it("uses a 15 second timeout per request", () => {
    expect(REQUEST_TIMEOUT_MS).toBe(15_000);
  });

  it("a request that never resolves ends as an error after REQUEST_TIMEOUT_MS instead of loading forever", async () => {
    const timeout = fakeAbortSignalTimeout();
    listActiveIncidents.mockImplementationOnce(hangUntilAborted);
    const { result } = renderIncidents("5803");
    expect(timeout).toHaveBeenCalledWith(REQUEST_TIMEOUT_MS);
    expect(listActiveIncidents).toHaveBeenCalledWith("5803", timeout.mock.results[0].value);

    await act(async () => vi.advanceTimersByTime(REQUEST_TIMEOUT_MS - 1));
    expect(result.current).toMatchObject({ data: null, error: null, isLoading: true });

    await act(async () => vi.advanceTimersByTime(1));
    expect(result.current).toMatchObject({ data: null, error: NETWORK_ERROR_MESSAGE, isLoading: false });
  });

  it("a hung poll times out and keeps the last data with the error", async () => {
    fakeAbortSignalTimeout();
    listActiveIncidents.mockResolvedValueOnce(paiList).mockImplementationOnce(hangUntilAborted);
    const { result } = renderIncidents(null);
    await flush();
    expect(result.current.data).toEqual(paiList);

    await act(async () => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
    expect(result.current.isLoading).toBe(true);
    await act(async () => vi.advanceTimersByTime(REQUEST_TIMEOUT_MS));
    expect(result.current).toMatchObject({ data: paiList, error: NETWORK_ERROR_MESSAGE, isLoading: false });
  });

  it("each request gets its own fresh timeout signal", async () => {
    const timeout = fakeAbortSignalTimeout();
    listActiveIncidents.mockResolvedValue(paiList);
    const { result } = renderIncidents(null);
    await flush();
    act(() => result.current.reload());
    await flush();
    expect(timeout).toHaveBeenCalledTimes(2);
    const [first, second] = listActiveIncidents.mock.calls.map((call) => call[1] as AbortSignal);
    expect(first).not.toBe(second);
  });

  it("the timeout of a previous district's request is ignored after switching", async () => {
    fakeAbortSignalTimeout();
    listActiveIncidents.mockImplementationOnce(hangUntilAborted).mockResolvedValueOnce(muangList);
    const { result, rerender } = renderIncidents("5803");
    rerender("5801");
    await flush();
    expect(result.current.data).toEqual(muangList);

    await act(async () => vi.advanceTimersByTime(REQUEST_TIMEOUT_MS));
    expect(result.current).toMatchObject({ data: muangList, error: null, isLoading: false });
  });
});

describe("useActiveIncidents — serverNow", () => {
  const GENERATED_AT = Date.parse(paiList.generated_at);

  it("is null while loading and after a first-load error", async () => {
    listActiveIncidents.mockRejectedValueOnce(new ApiError(500, "ระบบขัดข้อง"));
    const { result } = renderIncidents(null);
    expect(result.current.serverNow).toBeNull();
    await flush();
    expect(result.current.error).toBe("ระบบขัดข้อง");
    expect(result.current.serverNow).toBeNull();
  });

  it("equals generated_at right after the response, regardless of the client clock", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result } = renderIncidents(null);
    await flush();
    expect(result.current.serverNow).toBeInstanceOf(Date);
    expect(result.current.serverNow!.getTime()).toBe(GENERATED_AT);
    expect(result.current.serverNow!.getTime()).not.toBe(CLIENT_NOW.getTime());
  });

  it("adds the client time elapsed since the response was received", async () => {
    const first = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(first.promise);
    const { result } = renderIncidents(null);
    // The response arrives 5 s after the request was sent; that delay is not counted
    vi.setSystemTime(CLIENT_NOW.getTime() + 5_000);
    await act(async () => first.resolve(paiList));
    expect(result.current.serverNow!.getTime()).toBe(GENERATED_AT);

    const poll = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(poll.promise);
    act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
    expect(result.current.serverNow!.getTime()).toBe(GENERATED_AT + REFRESH_INTERVAL_MS);

    // A successful refresh re-bases on the new generated_at
    const refreshed = listOf([incident(1)], "2026-10-09T03:10:00Z");
    await act(async () => poll.resolve(refreshed));
    expect(result.current.serverNow!.getTime()).toBe(Date.parse("2026-10-09T03:10:00Z"));
  });

  it("keeps moving forward on each tick while refreshes fail", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList).mockRejectedValue(new ApiError(0, NETWORK_ERROR_MESSAGE));
    const { result } = renderIncidents(null);
    await flush();

    for (let tick = 1; tick <= 3; tick += 1) {
      act(() => vi.advanceTimersByTime(REFRESH_INTERVAL_MS));
      await flush();
      expect(result.current).toMatchObject({ data: paiList, error: NETWORK_ERROR_MESSAGE });
      expect(result.current.serverNow!.getTime()).toBe(GENERATED_AT + tick * REFRESH_INTERVAL_MS);
    }
  });

  it("is null after switching to another district until its data arrives", async () => {
    listActiveIncidents.mockResolvedValueOnce(paiList);
    const { result, rerender } = renderIncidents("5803");
    await flush();
    expect(result.current.serverNow).not.toBeNull();

    const next = deferred<ActiveIncidentList>();
    listActiveIncidents.mockReturnValueOnce(next.promise);
    rerender("5801");
    expect(result.current.serverNow).toBeNull();

    await act(async () => next.resolve(listOf([incident(2, "5801")], "2026-10-09T04:00:00Z")));
    expect(result.current.serverNow!.getTime()).toBe(Date.parse("2026-10-09T04:00:00Z"));
  });
});
