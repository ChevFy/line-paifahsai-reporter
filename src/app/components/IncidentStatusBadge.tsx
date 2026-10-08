import type { IncidentStatus } from "../types/admin";
import { INCIDENT_STATUS_LABELS } from "../utils/incident-labels";

export default function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  return <span className={`status-badge status-${status}`}>{INCIDENT_STATUS_LABELS[status]}</span>;
}
