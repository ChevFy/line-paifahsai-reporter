import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ACTIVE_INCIDENT_STATUSES,
    ActorType,
    AlertSeverity,
    District,
    Incident,
    IncidentEvent,
)
from services.admin_alerts import record_admin_alert
from services.jobs import enqueue_job
from services.volunteers import approved_line_user_ids_in_district

logger = logging.getLogger(__name__)

JOB_DISPATCH_INCIDENT = "dispatch_incident"
JOB_ESCALATE_INCIDENT = "escalate_incident"
ESCALATION_DELAY = timedelta(minutes=20)
EVENT_DISPATCHED = "dispatched"
ALERT_NO_VOLUNTEERS = "incident_no_volunteers"


class DispatchReason(StrEnum):
    INITIAL = "initial"
    ESCALATION = "escalation"
    ALL_WITHDRAWN = "all_withdrawn"


@dataclass(frozen=True)
class DispatchTarget:
    incident_id: int
    incident_public_id: uuid.UUID
    reason: DispatchReason
    latitude: float
    longitude: float
    district_code: str
    district_name: str
    province_name: str
    description: str | None
    created_at: datetime
    recipients: list[str]


async def enqueue_dispatch(
    session: AsyncSession,
    incident_id: int,
    reason: DispatchReason = DispatchReason.INITIAL,
    round_key: str | None = None,
) -> bool:
    round_key = round_key or reason.value
    return await enqueue_job(
        session,
        job_type=JOB_DISPATCH_INCIDENT,
        payload={"incident_id": incident_id, "reason": reason.value, "round": round_key},
        idempotency_key=f"{JOB_DISPATCH_INCIDENT}:{incident_id}:{round_key}",
    )


async def enqueue_escalation_check(
    session: AsyncSession,
    incident_id: int,
    now: datetime,
    round_key: str = DispatchReason.INITIAL.value,
    after_event_id: int = 0,
) -> bool:
    return await enqueue_job(
        session,
        job_type=JOB_ESCALATE_INCIDENT,
        payload={
            "incident_id": incident_id,
            "round": round_key,
            "after_event_id": after_event_id,
        },
        idempotency_key=f"{JOB_ESCALATE_INCIDENT}:{incident_id}:{round_key}",
        run_at=now + ESCALATION_DELAY,
    )


async def load_dispatch_target(
    session: AsyncSession,
    incident_id: int,
    reason: DispatchReason = DispatchReason.INITIAL,
) -> DispatchTarget | None:
    point = sa.cast(Incident.location, Geometry(geometry_type="POINT", srid=4326))
    statement = (
        sa.select(
            Incident.id,
            Incident.public_id,
            Incident.status,
            sa.func.ST_Y(point).label("latitude"),
            sa.func.ST_X(point).label("longitude"),
            Incident.district_code,
            District.name_th,
            District.province_name_th,
            Incident.description,
            Incident.created_at,
        )
        .join(District, District.code == Incident.district_code)
        .where(Incident.id == incident_id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise LookupError(f"incident {incident_id} not found")
    if row.status not in ACTIVE_INCIDENT_STATUSES:
        logger.info(
            "skip dispatch: incident_id=%s status=%s", incident_id, row.status
        )
        return None

    recipients = await approved_line_user_ids_in_district(session, row.district_code)
    return DispatchTarget(
        incident_id=row.id,
        incident_public_id=row.public_id,
        reason=reason,
        latitude=row.latitude,
        longitude=row.longitude,
        district_code=row.district_code,
        district_name=row.name_th,
        province_name=row.province_name_th,
        description=row.description,
        created_at=row.created_at,
        recipients=recipients,
    )


async def record_no_volunteers(session: AsyncSession, target: DispatchTarget) -> None:
    logger.error(
        "no approved volunteers for incident: incident_id=%s district=%s",
        target.incident_id,
        target.district_code,
    )
    await record_admin_alert(
        session,
        alert_type=ALERT_NO_VOLUNTEERS,
        severity=AlertSeverity.CRITICAL,
        message=(
            f"เหตุ #{target.incident_id} อำเภอ{target.district_name} "
            "ไม่มีจิตอาสาที่อนุมัติแล้วในอำเภอนี้ ระบบส่งหาใครไม่ได้ กรุณาประสานเอง"
        ),
        payload={
            "incident_id": target.incident_id,
            "district_code": target.district_code,
            "latitude": target.latitude,
            "longitude": target.longitude,
        },
        dedup_key=f"{ALERT_NO_VOLUNTEERS}:{target.incident_id}",
    )


async def record_dispatched(session: AsyncSession, target: DispatchTarget) -> None:
    session.add(
        IncidentEvent(
            incident_id=target.incident_id,
            event_type=EVENT_DISPATCHED,
            actor_type=ActorType.SYSTEM,
            payload={
                "recipient_count": len(target.recipients),
                "district_code": target.district_code,
                "reason": target.reason.value,
            },
        )
    )
    logger.info(
        "incident dispatched: incident_id=%s reason=%s district=%s recipients=%s",
        target.incident_id,
        target.reason,
        target.district_code,
        len(target.recipients),
    )
