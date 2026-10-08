import type { Volunteer, VolunteerAction, VolunteerFilters, VolunteerPage } from "../types/admin";
import { readApiError } from "../utils/api-error";
import { adminRequest } from "./api-client";

export async function listVolunteers(filters: VolunteerFilters): Promise<VolunteerPage> {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
  });
  if (filters.status) params.set("status", filters.status);
  if (filters.districtCode) params.set("district_code", filters.districtCode);

  const response = await adminRequest(`/admin/volunteers?${params}`);
  if (!response.ok) {
    throw await readApiError(response, "โหลดรายชื่อจิตอาสาไม่สำเร็จ");
  }

  return (await response.json()) as VolunteerPage;
}

export async function changeVolunteerStatus(
  volunteerId: number,
  action: VolunteerAction,
): Promise<Volunteer> {
  const response = await adminRequest(`/admin/volunteers/${volunteerId}/${action}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw await readApiError(response, "เปลี่ยนสถานะจิตอาสาไม่สำเร็จ");
  }

  return (await response.json()) as Volunteer;
}
