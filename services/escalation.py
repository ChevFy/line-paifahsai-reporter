import logging
from datetime import datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ACTIVE_INCIDENT_STATUSES,
    ActorType,
    AlertSeverity,
    Incident,
    IncidentEvent,
)
from services.admin_alerts import record_admin_alert
from services.assignments import ACTIVE_ASSIGNMENT_STATUSES, count_assignments
from services.dispatch import ESCALATION_DELAY, DispatchReason, enqueue_dispatch

logger = logging.getLogger(__name__)

EVENT_ESCALATED = "escalated"
ALERT_INCIDENT_UNACCEPTED = "incident_unaccepted"


class EscalationOutcome(StrEnum):
    ESCALATED = "escalated"
    HAS_VOLUNTEERS = "has_volunteers"
    INACTIVE = "inactive"


async def escalate_if_unaccepted(
    session: AsyncSession,
    incident_id: int,
    now: datetime,
) -> EscalationOutcome:
    incident = await session.get(Incident, incident_id, with_for_update=True)
    if incident is None:
        raise LookupError(f"incident {incident_id} not found")
    if incident.status not in ACTIVE_INCIDENT_STATUSES:
        logger.info(
            "escalation skipped, incident inactive: incident_id=%s status=%s",
            incident_id,
            incident.status,
        )
        return EscalationOutcome.INACTIVE

    active_count = await count_assignments(
        session, incident_id, ACTIVE_ASSIGNMENT_STATUSES
    )
    if active_count > 0:
        logger.info(
            "escalation skipped, volunteers assigned: incident_id=%s active=%s",
            incident_id,
            active_count,
        )
        return EscalationOutcome.HAS_VOLUNTEERS

    minutes = int(ESCALATION_DELAY.total_seconds() // 60)
    await enqueue_dispatch(session, incident_id, DispatchReason.ESCALATION)
    session.add(
        IncidentEvent(
            incident_id=incident_id,
            event_type=EVENT_ESCALATED,
            actor_type=ActorType.SYSTEM,
            payload={"after_minutes": minutes},
        )
    )
    await record_admin_alert(
        session,
        alert_type=ALERT_INCIDENT_UNACCEPTED,
        severity=AlertSeverity.CRITICAL,
        message=(
            f"เหตุ #{incident_id} ไม่มีจิตอาสารับงานภายใน {minutes} นาที "
            "ระบบส่งแจ้งเตือนซ้ำ 1 ครั้งแล้ว กรุณาประสานเอง"
        ),
        payload={"incident_id": incident_id, "district_code": incident.district_code},
        dedup_key=f"{ALERT_INCIDENT_UNACCEPTED}:{incident_id}",
    )
    logger.error(
        "incident escalated, no volunteer accepted: incident_id=%s after=%smin",
        incident_id,
        minutes,
    )
    return EscalationOutcome.ESCALATED
