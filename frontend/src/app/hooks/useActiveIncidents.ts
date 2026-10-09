import { useCallback, useEffect, useState } from "react";
import { listActiveIncidents } from "../services/incident-service";
import type { ActiveIncidentList } from "../types/admin";
import { errorMessage } from "../utils/api-error";

export const REFRESH_INTERVAL_MS = 60_000;
export const REQUEST_TIMEOUT_MS = 15_000;

type LoadResult = {
  districtCode: string | null;
  reloadCount: number;
  data: ActiveIncidentList | null;
  receivedAt: number | null;
  error: string | null;
};

// Polls so a dashboard left open keeps showing new fires without a manual refresh
export function useActiveIncidents(districtCode: string | null) {
  const [reloadCount, setReloadCount] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [result, setResult] = useState<LoadResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Without a timeout a hung backend would keep every poll in flight and never surface an error
    listActiveIncidents(districtCode, AbortSignal.timeout(REQUEST_TIMEOUT_MS))
      .then((data) => {
        if (!cancelled) {
          setResult({ districtCode, reloadCount, data, receivedAt: Date.now(), error: null });
        }
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        // A failed refresh keeps the last pins on screen; the error stays until a refresh succeeds
        setResult((previous) => {
          const isSameDistrict = previous?.districtCode === districtCode;
          return {
            districtCode,
            reloadCount,
            data: isSameDistrict ? previous.data : null,
            receivedAt: isSameDistrict ? previous.receivedAt : null,
            error: errorMessage(reason, "โหลดเหตุที่กำลังเกิดไม่สำเร็จ"),
          };
        });
      });
    return () => {
      cancelled = true;
    };
  }, [districtCode, reloadCount]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
      setReloadCount((count) => count + 1);
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  const reload = useCallback(() => setReloadCount((count) => count + 1), []);

  const isSameDistrict = result?.districtCode === districtCode;
  const data = isSameDistrict ? result.data : null;
  const receivedAt = isSameDistrict ? result.receivedAt : null;

  // Server time "now", so elapsed times keep moving even when refreshes fail and
  // do not depend on the admin's clock being correct
  const serverNow =
    data && receivedAt !== null
      ? new Date(Date.parse(data.generated_at) + Math.max(0, now - receivedAt))
      : null;

  return {
    data,
    serverNow,
    error: isSameDistrict ? result.error : null,
    isLoading: !(isSameDistrict && result.reloadCount === reloadCount),
    reload,
  };
}
