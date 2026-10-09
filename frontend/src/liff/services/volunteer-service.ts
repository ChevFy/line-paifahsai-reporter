import { getApiError } from "../utils/api-error";
import type { VolunteerCreate, VolunteerRegistrationResponse } from "../types/volunteer";
import { authenticatedRequest } from "./api-client";

export async function registerVolunteer(
  payload: VolunteerCreate,
): Promise<VolunteerRegistrationResponse> {
  const response = await authenticatedRequest("/volunteers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await getApiError(response, "registerVolunteer");
  }

  return (await response.json()) as VolunteerRegistrationResponse;
}

// Returns null when the user has not registered yet (backend answers 404)
export async function getMyVolunteer(): Promise<VolunteerRegistrationResponse | null> {
  const response = await authenticatedRequest("/volunteers/me");

  if (response.status === 404) return null;
  if (!response.ok) {
    throw await getApiError(response, "loadVolunteer");
  }

  return (await response.json()) as VolunteerRegistrationResponse;
}
