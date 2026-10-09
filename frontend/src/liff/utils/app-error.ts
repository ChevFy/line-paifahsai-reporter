import type { Translation } from "../hooks/language-context";

export type ErrorCode = keyof Translation["errors"];

// Carries a translation key so the message follows the current language at render time
export class AppError extends Error {
  readonly code: ErrorCode;

  constructor(code: ErrorCode) {
    super(code);
    this.name = "AppError";
    this.code = code;
  }
}

// `code` is translated at render; `message` (from the backend) is shown as-is
export type DisplayError = { code: ErrorCode } | { message: string };

export function toDisplayError(reason: unknown, fallback: ErrorCode): DisplayError {
  if (reason instanceof AppError) return { code: reason.code };
  if (reason instanceof Error && reason.message) return { message: reason.message };
  return { code: fallback };
}

export function formatError(error: DisplayError, t: Translation): string {
  return "code" in error ? t.errors[error.code] : error.message;
}
