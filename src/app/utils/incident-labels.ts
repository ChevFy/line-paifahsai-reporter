import type { IncidentStatus } from "../types/admin";

export const INCIDENT_STATUS_LABELS: Record<IncidentStatus, string> = {
  open: "ยังไม่มีคนรับ",
  in_progress: "มีจิตอาสารับแล้ว",
};
