import logging
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ACTIVE_INCIDENT_STATUSES,
    ActorType,
    AlertSeverity,
    Incident,
    IncidentEvent,
)
from services.admin_alerts import record_admin_alert
from services.assignments import (
    ACTIVE_ASSIGNMENT_STATUSES,
    EVENT_ALL_WITHDRAWN,
    count_assignments,
)
from services.dispatch import ESCALATION_DELAY, DispatchReason, enqueue_dispatch

logger = logging.getLogger(__name__)

EVENT_ESCALATED = "escalated"
ALERT_INCIDENT_UNACCEPTED = "incident_unaccepted"


class EscalationOutcome(StrEnum):
    ESCALATED = "escalated"
    HAS_VOLUNTEERS = "has_volunteers"
    INACTIVE = "inactive"
    SUPERSEDED = "superseded"


async def escalate_if_unaccepted(
    session: AsyncSession,
    incident_id: int,
    now: datetime,
    round_key: str = DispatchReason.INITIAL.value,
    after_event_id: int = 0,
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

    newer_round = (
        await session.execute(
            sa.select(IncidentEvent.id)
            .where(
                IncidentEvent.incident_id == incident_id,
                IncidentEvent.event_type == EVENT_ALL_WITHDRAWN,
                IncidentEvent.id > after_event_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if newer_round is not None:
        logger.info(
            "escalation skipped, superseded by newer round: incident_id=%s "
            "round=%s newer_event_id=%s",
            incident_id,
            round_key,
            newer_round,
        )
        return EscalationOutcome.SUPERSEDED

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
    await enqueue_dispatch(
        session,
        incident_id,
        DispatchReason.ESCALATION,
        round_key=f"{DispatchReason.ESCALATION.value}:{round_key}",
    )
    session.add(
        IncidentEvent(
            incident_id=incident_id,
            event_type=EVENT_ESCALATED,
            actor_type=ActorType.SYSTEM,
            payload={"after_minutes": minutes, "round": round_key},
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
        payload={
            "incident_id": incident_id,
            "district_code": incident.district_code,
            "round": round_key,
        },
        dedup_key=f"{ALERT_INCIDENT_UNACCEPTED}:{incident_id}",
    )
    logger.error(
        "incident escalated, no volunteer accepted: incident_id=%s round=%s "
        "after=%smin",
        incident_id,
        round_key,
        minutes,
    )
    return EscalationOutcome.ESCALATED
