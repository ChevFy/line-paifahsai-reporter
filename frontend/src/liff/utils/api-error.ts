import type { ApiErrorResponse } from "../types/report";
import { AppError } from "./app-error";
import type { ErrorCode } from "./app-error";

export async function getApiError(
  response: Response,
  fallback: ErrorCode,
): Promise<Error> {
  try {
    const body = (await response.json()) as ApiErrorResponse;
    const message = body.detail?.message;
    return message ? new Error(message) : new AppError(fallback);
  } catch {
    return new AppError(fallback);
  }
}
