import type { ApiErrorResponse } from "../types/report";

export async function getApiErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorResponse;
    return body.detail?.message ?? fallback;
  } catch {
    return fallback;
  }
}
