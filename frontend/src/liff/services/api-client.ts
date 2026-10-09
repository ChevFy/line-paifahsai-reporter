import { API_BASE_URL } from "../config/api";
import liff from "../../liff";
import { AppError } from "../utils/app-error";

export async function request(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new AppError("network");
  }
}

export async function authenticatedRequest(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = liff.getIDToken();
  if (!token) {
    throw new AppError("notLoggedIn");
  }

  return request(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });
}
