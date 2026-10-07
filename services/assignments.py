import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ACTIVE_INCIDENT_STATUSES,
    ActorType,
    Assignment,
    AssignmentStatus,
    Incident,
    IncidentEvent,
    IncidentStatus,
    VolunteerStatus,
)
from services.volunteers import find_volunteer_by_line_user

logger = logging.getLogger(__name__)

EVENT_VOLUNTEER_ACCEPTED = "volunteer_accepted"


class AcceptOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJOINED = "rejoined"
    ALREADY_ACCEPTED = "already_accepted"
    NOT_VOLUNTEER = "not_volunteer"
    INCIDENT_NOT_FOUND = "incident_not_found"
    INCIDENT_CLOSED = "incident_closed"


@dataclass(frozen=True)
class AcceptResult:
    outcome: AcceptOutcome
    incident_id: int
    active_volunteer_count: int = 0


async def accept_incident(
    session: AsyncSession,
    line_user_id: str,
    incident_id: int,
    now: datetime,
) -> AcceptResult:
    volunteer = await find_volunteer_by_line_user(session, line_user_id)
    if volunteer is None or volunteer.status != VolunteerStatus.APPROVED:
        logger.warning(
            "accept rejected, not an approved volunteer: line_user_id=%s incident_id=%s",
            line_user_id,
            incident_id,
        )
        return AcceptResult(AcceptOutcome.NOT_VOLUNTEER, incident_id)

    incident = await session.get(Incident, incident_id, with_for_update=True)
    if incident is None:
        logger.warning("accept for unknown incident: incident_id=%s", incident_id)
        return AcceptResult(AcceptOutcome.INCIDENT_NOT_FOUND, incident_id)
    if incident.status not in ACTIVE_INCIDENT_STATUSES:
        logger.info(
            "accept on inactive incident: incident_id=%s status=%s volunteer_id=%s",
            incident_id,
            incident.status,
            volunteer.id,
        )
        return AcceptResult(AcceptOutcome.INCIDENT_CLOSED, incident_id)

    inserted_id = (
        await session.execute(
            insert(Assignment)
            .values(incident_id=incident_id, volunteer_id=volunteer.id)
            .on_conflict_do_nothing(
                index_elements=[Assignment.incident_id, Assignment.volunteer_id]
            )
            .returning(Assignment.id)
        )
    ).scalar_one_or_none()

    if inserted_id is not None:
        outcome = AcceptOutcome.ACCEPTED
        assignment_id = inserted_id
    else:
        assignment = (
            await session.execute(
                sa.select(Assignment).where(
                    Assignment.incident_id == incident_id,
                    Assignment.volunteer_id == volunteer.id,
                )
            )
        ).scalar_one()
        assignment_id = assignment.id
        if assignment.status == AssignmentStatus.WITHDRAWN:
            assignment.status = AssignmentStatus.ACCEPTED
            assignment.accepted_at = now
            outcome = AcceptOutcome.REJOINED
        else:
            outcome = AcceptOutcome.ALREADY_ACCEPTED

    if outcome != AcceptOutcome.ALREADY_ACCEPTED:
        if incident.status == IncidentStatus.OPEN:
            incident.status = IncidentStatus.IN_PROGRESS
        session.add(
            IncidentEvent(
                incident_id=incident_id,
                event_type=EVENT_VOLUNTEER_ACCEPTED,
                actor_type=ActorType.VOLUNTEER,
                actor_id=line_user_id,
                payload={
                    "assignment_id": assignment_id,
                    "volunteer_id": volunteer.id,
                    "outcome": outcome.value,
                },
            )
        )
    await session.flush()

    active_count = (
        await session.execute(
            sa.select(sa.func.count(Assignment.id)).where(
                Assignment.incident_id == incident_id,
                Assignment.status != AssignmentStatus.WITHDRAWN,
            )
        )
    ).scalar_one()

    logger.info(
        "volunteer accept: incident_id=%s volunteer_id=%s outcome=%s active=%s",
        incident_id,
        volunteer.id,
        outcome,
        active_count,
    )
    return AcceptResult(outcome, incident_id, active_count)
