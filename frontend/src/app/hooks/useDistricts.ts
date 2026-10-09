import { useEffect, useState } from "react";
import { listDistricts } from "../services/district-service";
import type { District } from "../types/admin";
import { errorMessage } from "../utils/api-error";

export function useDistricts() {
  const [districts, setDistricts] = useState<District[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDistricts()
      .then((result) => {
        if (!cancelled) setDistricts(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(errorMessage(reason, "โหลดรายชื่ออำเภอไม่สำเร็จ"));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { districts, error };
}
