import { ApiError, NETWORK_ERROR_MESSAGE } from "../utils/api-error";

let onUnauthorized: () => void = () => undefined;

// AuthProvider registers this so any 401 (e.g. the 12-hour session expiring)
// signs the admin out and sends them back to the login page.
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

export async function request(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init);
  } catch {
    throw new ApiError(0, NETWORK_ERROR_MESSAGE);
  }
}

export async function adminRequest(path: string, init?: RequestInit): Promise<Response> {
  const response = await request(path, init);
  if (response.status === 401) {
    onUnauthorized();
  }
  return response;
}
