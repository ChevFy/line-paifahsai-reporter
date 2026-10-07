from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ACTIVE_INCIDENT_STATUSES,
    Assignment,
    District,
    Incident,
    IncidentStatus,
    Report,
    Volunteer,
)
from services.assignments import ACTIVE_ASSIGNMENT_STATUSES
from services.volunteers import approved_line_user_ids_in_district


@dataclass(frozen=True)
class AssignmentSummary:
    incident_id: int
    district_name: str
    volunteer_names: list[str]
    recipients: list[str]


@dataclass(frozen=True)
class ClosureNotice:
    incident_id: int
    district_name: str
    reporter_ids: list[str]
    volunteer_ids: list[str]


async def load_incident_district(
    session: AsyncSession,
    incident_id: int,
) -> tuple[IncidentStatus, str, str]:
    statement = (
        sa.select(Incident.status, Incident.district_code, District.name_th)
        .join(District, District.code == Incident.district_code)
        .where(Incident.id == incident_id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise LookupError(f"incident {incident_id} not found")
    return row.status, row.district_code, row.name_th


async def load_assignment_summary(
    session: AsyncSession,
    incident_id: int,
) -> AssignmentSummary | None:
    status, district_code, district_name = await load_incident_district(
        session, incident_id
    )
    if status not in ACTIVE_INCIDENT_STATUSES:
        return None

    assigned = (
        await session.execute(
            sa.select(Volunteer.full_name, Volunteer.line_user_id)
            .join(Assignment, Assignment.volunteer_id == Volunteer.id)
            .where(
                Assignment.incident_id == incident_id,
                Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            )
            .order_by(Assignment.accepted_at, Assignment.id)
        )
    ).all()

    recipients = await approved_line_user_ids_in_district(session, district_code)
    for row in assigned:
        if row.line_user_id not in recipients:
            recipients.append(row.line_user_id)

    return AssignmentSummary(
        incident_id=incident_id,
        district_name=district_name,
        volunteer_names=[row.full_name for row in assigned],
        recipients=recipients,
    )


async def load_closure_notice(
    session: AsyncSession,
    incident_id: int,
) -> ClosureNotice:
    _, _, district_name = await load_incident_district(session, incident_id)

    reporter_ids = (
        await session.execute(
            sa.select(Report.reporter_user_id)
            .where(Report.incident_id == incident_id)
            .group_by(Report.reporter_user_id)
            .order_by(sa.func.min(Report.id))
        )
    ).scalars().all()
    volunteer_ids = (
        await session.execute(
            sa.select(Volunteer.line_user_id)
            .join(Assignment, Assignment.volunteer_id == Volunteer.id)
            .where(Assignment.incident_id == incident_id)
            .order_by(Assignment.id)
        )
    ).scalars().all()

    return ClosureNotice(
        incident_id=incident_id,
        district_name=district_name,
        reporter_ids=list(reporter_ids),
        volunteer_ids=list(volunteer_ids),
    )
