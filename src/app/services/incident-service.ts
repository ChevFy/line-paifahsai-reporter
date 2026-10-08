import type { ActiveIncidentList } from "../types/admin";
import { readApiError } from "../utils/api-error";
import { request } from "./api-client";

export async function listActiveIncidents(
  districtCode: string | null,
  signal?: AbortSignal,
): Promise<ActiveIncidentList> {
  const query = districtCode ? `?${new URLSearchParams({ district_code: districtCode })}` : "";
  const response = await request(`/incidents/active${query}`, { signal });
  if (!response.ok) {
    throw await readApiError(response, "โหลดเหตุที่กำลังเกิดไม่สำเร็จ");
  }

  return (await response.json()) as ActiveIncidentList;
}
