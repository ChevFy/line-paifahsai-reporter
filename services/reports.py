import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from geoalchemy2 import WKTElement
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ActorType,
    AlertSeverity,
    District,
    Incident,
    IncidentEvent,
    IncidentStatus,
    LineUser,
    Report,
)
from services.admin_alerts import record_admin_alert
from services.ops_date import ops_date_for

logger = logging.getLogger(__name__)

DEDUP_RADIUS_METERS = 1000
DEDUP_CLOSED_WINDOW = timedelta(hours=6)
DEDUP_LOCK_NAME = "incident_dedup"
ACTIVE_STATUSES = (IncidentStatus.OPEN, IncidentStatus.IN_PROGRESS)

EVENT_INCIDENT_CREATED = "incident_created"
EVENT_REPORT_ATTACHED = "report_attached"
ALERT_REPORT_ON_CLOSED_INCIDENT = "report_on_recently_closed_incident"
ALERT_INCIDENT_NEEDS_DISPATCH = "incident_needs_dispatch"


class ReportOutcome(StrEnum):
    NEW_INCIDENT = "new_incident"
    MERGED = "merged"
    MERGED_RECENTLY_CLOSED = "merged_recently_closed"
    DUPLICATE_REQUEST = "duplicate_request"


@dataclass(frozen=True)
class ReportSubmission:
    reporter_user_id: str
    reporter_display_name: str | None
    client_request_id: UUID
    latitude: float
    longitude: float
    district_code: str
    description: str | None


@dataclass(frozen=True)
class ReportResult:
    report_id: int
    incident_id: int
    outcome: ReportOutcome


class UnknownDistrictError(Exception):
    pass


class ReporterBlockedError(Exception):
    pass


async def submit_report(
    session: AsyncSession,
    submission: ReportSubmission,
    now: datetime,
) -> ReportResult:
    is_blocked = await upsert_reporter(session, submission)
    if is_blocked:
        raise ReporterBlockedError(submission.reporter_user_id)

    await acquire_dedup_lock(session)

    existing = await find_report_by_client_request_id(session, submission)
    if existing is not None:
        logger.info(
            "duplicate report request: report_id=%s client_request_id=%s",
            existing.id,
            submission.client_request_id,
        )
        return ReportResult(
            report_id=existing.id,
            incident_id=existing.incident_id,
            outcome=ReportOutcome.DUPLICATE_REQUEST,
        )

    if await session.get(District, submission.district_code) is None:
        raise UnknownDistrictError(submission.district_code)

    ewkt = f"SRID=4326;POINT({submission.longitude} {submission.latitude})"
    ops_date = ops_date_for(now)

    incident = await find_matching_incident(session, ewkt, now)
    if incident is None:
        incident = Incident(
            location=WKTElement(ewkt, extended=True),
            description=submission.description,
            district_code=submission.district_code,
            ops_date=ops_date,
        )
        session.add(incident)
        await session.flush()
        outcome = ReportOutcome.NEW_INCIDENT
    elif incident.status == IncidentStatus.CLOSED:
        outcome = ReportOutcome.MERGED_RECENTLY_CLOSED
    else:
        outcome = ReportOutcome.MERGED

    report = Report(
        incident_id=incident.id,
        reporter_user_id=submission.reporter_user_id,
        location=WKTElement(ewkt, extended=True),
        description=submission.description,
        ops_date=ops_date,
        client_request_id=submission.client_request_id,
    )
    session.add(report)
    await session.flush()

    session.add(
        IncidentEvent(
            incident_id=incident.id,
            event_type=(
                EVENT_INCIDENT_CREATED
                if outcome == ReportOutcome.NEW_INCIDENT
                else EVENT_REPORT_ATTACHED
            ),
            actor_type=ActorType.REPORTER,
            actor_id=submission.reporter_user_id,
            payload={"report_id": report.id, "outcome": outcome.value},
        )
    )
    await session.execute(
        sa.update(LineUser)
        .where(LineUser.user_id == submission.reporter_user_id)
        .values(report_count=LineUser.report_count + 1)
    )

    if outcome == ReportOutcome.NEW_INCIDENT:
        await record_admin_alert(
            session,
            alert_type=ALERT_INCIDENT_NEEDS_DISPATCH,
            severity=AlertSeverity.CRITICAL,
            message=(
                f"มีเหตุใหม่ incident #{incident.id} อำเภอ {submission.district_code} "
                "ระบบยังไม่ส่งหาจิตอาสาอัตโนมัติ กรุณาประสานจิตอาสาเอง"
            ),
            payload={
                "incident_id": incident.id,
                "report_id": report.id,
                "district_code": submission.district_code,
                "latitude": submission.latitude,
                "longitude": submission.longitude,
            },
            dedup_key=f"{ALERT_INCIDENT_NEEDS_DISPATCH}:{incident.id}",
        )

    if outcome == ReportOutcome.MERGED_RECENTLY_CLOSED:
        await record_admin_alert(
            session,
            alert_type=ALERT_REPORT_ON_CLOSED_INCIDENT,
            severity=AlertSeverity.CRITICAL,
            message=(
                f"มีผู้แจ้งเหตุใกล้ incident #{incident.id} ที่เพิ่งปิดไป "
                "อาจเป็นไฟปะทุซ้ำ กรุณาตรวจสอบ"
            ),
            payload={"incident_id": incident.id, "report_id": report.id},
            dedup_key=f"{ALERT_REPORT_ON_CLOSED_INCIDENT}:{incident.id}",
        )

    logger.info(
        "report submitted: report_id=%s incident_id=%s outcome=%s district=%s",
        report.id,
        incident.id,
        outcome,
        submission.district_code,
    )
    return ReportResult(report_id=report.id, incident_id=incident.id, outcome=outcome)


async def upsert_reporter(session: AsyncSession, submission: ReportSubmission) -> bool:
    statement = insert(LineUser).values(
        user_id=submission.reporter_user_id,
        display_name=submission.reporter_display_name,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[LineUser.user_id],
        set_={
            "display_name": sa.func.coalesce(
                statement.excluded.display_name, LineUser.display_name
            )
        },
    ).returning(LineUser.is_blocked)
    return (await session.execute(statement)).scalar_one()


async def acquire_dedup_lock(session: AsyncSession) -> None:
    await session.execute(
        sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtext(DEDUP_LOCK_NAME)))
    )


async def find_report_by_client_request_id(
    session: AsyncSession,
    submission: ReportSubmission,
) -> Report | None:
    statement = sa.select(Report).where(
        Report.reporter_user_id == submission.reporter_user_id,
        Report.client_request_id == submission.client_request_id,
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def find_matching_incident(
    session: AsyncSession,
    ewkt: str,
    now: datetime,
) -> Incident | None:
    point = sa.func.ST_GeogFromText(ewkt)
    is_active = Incident.status.in_(ACTIVE_STATUSES)
    statement = (
        sa.select(Incident)
        .where(
            sa.func.ST_DWithin(Incident.location, point, DEDUP_RADIUS_METERS),
            sa.or_(
                is_active,
                sa.and_(
                    Incident.status == IncidentStatus.CLOSED,
                    Incident.closed_at >= now - DEDUP_CLOSED_WINDOW,
                ),
            ),
        )
        .order_by(
            sa.case((is_active, 0), else_=1),
            sa.func.ST_Distance(Incident.location, point),
            Incident.id,
        )
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()
