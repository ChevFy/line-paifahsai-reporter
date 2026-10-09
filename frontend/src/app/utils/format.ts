const dateTimeFormat = new Intl.DateTimeFormat("th-TH", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Bangkok",
});

const timeFormat = new Intl.DateTimeFormat("th-TH", {
  timeStyle: "short",
  timeZone: "Asia/Bangkok",
});

const relativeTimeFormat = new Intl.RelativeTimeFormat("th-TH", { numeric: "always" });

function parseDate(value: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value: string | null): string {
  const date = parseDate(value);
  return date ? dateTimeFormat.format(date) : "–";
}

export function formatTime(value: string | null): string {
  const date = parseDate(value);
  return date ? timeFormat.format(date) : "–";
}

// Rounds down so "1 ชั่วโมงที่แล้ว" never shows for something only 31 minutes old
export function formatElapsed(value: string, now: Date): string {
  const date = parseDate(value);
  if (!date) return "–";
  const minutes = Math.max(0, Math.floor((now.getTime() - date.getTime()) / 60_000));
  if (minutes < 60) return relativeTimeFormat.format(-minutes, "minute");
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return relativeTimeFormat.format(-hours, "hour");
  return relativeTimeFormat.format(-Math.floor(hours / 24), "day");
}
