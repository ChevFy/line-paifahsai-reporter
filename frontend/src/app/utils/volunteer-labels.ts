import type { VolunteerStatus } from "../types/admin";

export const STATUS_LABELS: Record<VolunteerStatus, string> = {
  pending: "รออนุมัติ",
  approved: "อนุมัติแล้ว",
  rejected: "ไม่อนุมัติ",
  suspended: "ระงับ",
};
