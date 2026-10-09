import type { VolunteerStatus } from "../types/admin";
import { STATUS_LABELS } from "../utils/volunteer-labels";

export default function StatusBadge({ status }: { status: VolunteerStatus }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABELS[status]}</span>;
}
