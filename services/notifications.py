import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ACTIVE_INCIDENT_STATUSES,
    Assignment,
    District,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Report,
    Volunteer,
)
from services.assignments import (
    ACTION_EVENTS,
    ACTIVE_ASSIGNMENT_STATUSES,
    EVENT_VOLUNTEER_ACCEPTED,
    AssignmentAction,
    summary_window_bounds,
)
from services.volunteers import approved_line_user_ids_in_district

EVENT_VOLUNTEER_WITHDRAWN = ACTION_EVENTS[AssignmentAction.WITHDRAW]


@dataclass(frozen=True)
class AssignmentSummary:
    incident_id: int
    incident_public_id: uuid.UUID
    district_name: str
    volunteer_names: list[str]
    recipients: list[str]
    joined_names: list[str] = field(default_factory=list)
    withdrawn_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClosureNotice:
    incident_id: int
    incident_public_id: uuid.UUID
    district_name: str
    reporter_ids: list[str]
    volunteer_ids: list[str]
    closed_by_name: str | None = None


@dataclass(frozen=True)
class IncidentRef:
    public_id: uuid.UUID
    status: IncidentStatus
    district_code: str
    district_name: str


async def load_incident_district(
    session: AsyncSession,
    incident_id: int,
) -> IncidentRef:
    statement = (
        sa.select(
            Incident.public_id,
            Incident.status,
            Incident.district_code,
            District.name_th,
        )
        .join(District, District.code == Incident.district_code)
        .where(Incident.id == incident_id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise LookupError(f"incident {incident_id} not found")
    return IncidentRef(
        public_id=row.public_id,
        status=row.status,
        district_code=row.district_code,
        district_name=row.name_th,
    )


async def load_window_changes(
    session: AsyncSession,
    incident_id: int,
    window: int,
) -> tuple[list[str], list[str]]:
    start, end = summary_window_bounds(window)
    rows = (
        await session.execute(
            sa.select(IncidentEvent.event_type, Volunteer.full_name)
            .join(
                Volunteer,
                Volunteer.id == IncidentEvent.payload["volunteer_id"].as_integer(),
            )
            .where(
                IncidentEvent.incident_id == incident_id,
                IncidentEvent.event_type.in_(
                    (EVENT_VOLUNTEER_ACCEPTED, EVENT_VOLUNTEER_WITHDRAWN)
                ),
                IncidentEvent.created_at >= start,
                IncidentEvent.created_at < end,
            )
            .order_by(IncidentEvent.id)
        )
    ).all()

    joined: list[str] = []
    withdrawn: list[str] = []
    for row in rows:
        names = joined if row.event_type == EVENT_VOLUNTEER_ACCEPTED else withdrawn
        if row.full_name not in names:
            names.append(row.full_name)
    return joined, withdrawn


async def load_assignment_summary(
    session: AsyncSession,
    incident_id: int,
    window: int | None = None,
) -> AssignmentSummary | None:
    incident = await load_incident_district(session, incident_id)
    if incident.status not in ACTIVE_INCIDENT_STATUSES:
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

    recipients = await approved_line_user_ids_in_district(
        session, incident.district_code
    )
    for row in assigned:
        if row.line_user_id not in recipients:
            recipients.append(row.line_user_id)

    joined, withdrawn = (
        await load_window_changes(session, incident_id, window)
        if window is not None
        else ([], [])
    )
    return AssignmentSummary(
        incident_id=incident_id,
        incident_public_id=incident.public_id,
        district_name=incident.district_name,
        volunteer_names=[row.full_name for row in assigned],
        recipients=recipients,
        joined_names=joined,
        withdrawn_names=withdrawn,
    )


async def load_closure_notice(
    session: AsyncSession,
    incident_id: int,
    closed_by_volunteer_id: int | None = None,
) -> ClosureNotice:
    incident = await load_incident_district(session, incident_id)

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
    recipients = list(volunteer_ids)
    for line_user_id in await approved_line_user_ids_in_district(
        session, incident.district_code
    ):
        if line_user_id not in recipients:
            recipients.append(line_user_id)

    closed_by_name = (
        await session.scalar(
            sa.select(Volunteer.full_name).where(
                Volunteer.id == closed_by_volunteer_id
            )
        )
        if closed_by_volunteer_id is not None
        else None
    )
    return ClosureNotice(
        incident_id=incident_id,
        incident_public_id=incident.public_id,
        district_name=incident.district_name,
        reporter_ids=list(reporter_ids),
        volunteer_ids=recipients,
        closed_by_name=closed_by_name,
    )
