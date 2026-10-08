export const NETWORK_ERROR_MESSAGE =
  "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองอีกครั้ง";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ApiErrorBody = {
  detail?: {
    message?: unknown;
  };
};

export async function readApiError(response: Response, fallback: string): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    const message = body.detail?.message;
    return new ApiError(response.status, typeof message === "string" && message ? message : fallback);
  } catch {
    return new ApiError(response.status, fallback);
  }
}

// Only messages we produced (backend detail.message or our own fallbacks) reach the
// screen; anything else, e.g. a JSON parse error, could leak internals
export function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof ApiError && reason.message ? reason.message : fallback;
}
