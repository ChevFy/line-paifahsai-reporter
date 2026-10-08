const dateTimeFormat = new Intl.DateTimeFormat("th-TH", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Bangkok",
});

export function formatDateTime(value: string | null): string {
  if (!value) return "–";
  return dateTimeFormat.format(new Date(value));
}
