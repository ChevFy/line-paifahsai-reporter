import type { District } from "../types/admin";
import { readApiError } from "../utils/api-error";
import { request } from "./api-client";

export async function listDistricts(): Promise<District[]> {
  const response = await request("/districts");
  if (!response.ok) {
    throw await readApiError(response, "โหลดรายชื่ออำเภอไม่สำเร็จ");
  }

  return (await response.json()) as District[];
}
