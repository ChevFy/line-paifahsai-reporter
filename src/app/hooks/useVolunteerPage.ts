import { useCallback, useEffect, useState } from "react";
import { listVolunteers } from "../services/volunteer-service";
import type { VolunteerFilters, VolunteerPage } from "../types/admin";
import { errorMessage } from "../utils/api-error";

type LoadResult = {
  filterKey: string;
  reloadCount: number;
  page: VolunteerPage | null;
  error: string | null;
};

export function useVolunteerPage({ status, districtCode, limit, offset }: VolunteerFilters) {
  const [reloadCount, setReloadCount] = useState(0);
  const [result, setResult] = useState<LoadResult | null>(null);
  const filterKey = JSON.stringify([status, districtCode, limit, offset]);

  useEffect(() => {
    let cancelled = false;
    listVolunteers({ status, districtCode, limit, offset })
      .then((page) => {
        if (!cancelled) setResult({ filterKey, reloadCount, page, error: null });
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        // A failed refresh of the same filter keeps its rows; a new filter never shows old rows
        setResult((previous) => ({
          filterKey,
          reloadCount,
          page: previous?.filterKey === filterKey ? previous.page : null,
          error: errorMessage(reason, "โหลดรายชื่อจิตอาสาไม่สำเร็จ"),
        }));
      });
    return () => {
      cancelled = true;
    };
  }, [status, districtCode, limit, offset, filterKey, reloadCount]);

  const reload = useCallback(() => setReloadCount((count) => count + 1), []);

  const isSameFilter = result?.filterKey === filterKey;
  const isCurrent = isSameFilter && result.reloadCount === reloadCount;

  return {
    page: isSameFilter ? result.page : null,
    error: isCurrent ? result.error : null,
    isLoading: !isCurrent,
    reload,
  };
}
