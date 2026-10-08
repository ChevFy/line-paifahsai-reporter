import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ACTIVE_INCIDENT_STATUSES,
    ActorType,
    AlertSeverity,
    Assignment,
    AssignmentStatus,
    Incident,
    IncidentEvent,
    IncidentStatus,
    VolunteerStatus,
)
from services.admin_alerts import record_admin_alert
from services.dispatch import (
    DispatchReason,
    enqueue_dispatch,
    enqueue_escalation_check,
)
from services.jobs import enqueue_job
from services.volunteers import find_volunteer_by_line_user

logger = logging.getLogger(__name__)

EVENT_VOLUNTEER_ACCEPTED = "volunteer_accepted"
EVENT_INCIDENT_CLOSED = "incident_closed"
EVENT_ALL_WITHDRAWN = "all_volunteers_withdrawn"
ALERT_ALL_WITHDRAWN = "incident_all_withdrawn"
JOB_ASSIGNMENT_SUMMARY = "notify_assignment_summary"
JOB_INCIDENT_CLOSED = "notify_incident_closed"
SUMMARY_WINDOW = timedelta(minutes=2)
ACTIVE_ASSIGNMENT_STATUSES = (AssignmentStatus.ACCEPTED, AssignmentStatus.ARRIVED)


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


class AssignmentAction(StrEnum):
    ARRIVED = "arrived"
    DONE = "done"
    WITHDRAW = "withdraw"


TRANSITIONS: dict[AssignmentAction, tuple[set[AssignmentStatus], AssignmentStatus]] = {
    AssignmentAction.ARRIVED: ({AssignmentStatus.ACCEPTED}, AssignmentStatus.ARRIVED),
    AssignmentAction.DONE: (set(ACTIVE_ASSIGNMENT_STATUSES), AssignmentStatus.DONE),
    AssignmentAction.WITHDRAW: (
        set(ACTIVE_ASSIGNMENT_STATUSES),
        AssignmentStatus.WITHDRAWN,
    ),
}
ACTION_EVENTS = {
    AssignmentAction.ARRIVED: "volunteer_arrived",
    AssignmentAction.DONE: "volunteer_done",
    AssignmentAction.WITHDRAW: "volunteer_withdrawn",
}


class UpdateOutcome(StrEnum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    INVALID_TRANSITION = "invalid_transition"
    NOT_ASSIGNED = "not_assigned"
    VOLUNTEER_NOT_APPROVED = "volunteer_not_approved"
    INCIDENT_NOT_FOUND = "incident_not_found"
    INCIDENT_CLOSED = "incident_closed"


@dataclass(frozen=True)
class UpdateResult:
    outcome: UpdateOutcome
    incident_id: int
    action: AssignmentAction
    assignment_status: AssignmentStatus | None = None
    active_volunteer_count: int = 0
    incident_closed: bool = False
    all_withdrawn: bool = False


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
        assignment = await find_assignment(session, incident_id, volunteer.id)
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
                created_at=now,
            )
        )
        await enqueue_assignment_summary(session, incident_id, now)
    await session.flush()

    active_count = await count_assignments(
        session, incident_id, ACTIVE_ASSIGNMENT_STATUSES
    )
    logger.info(
        "volunteer accept: incident_id=%s volunteer_id=%s outcome=%s active=%s",
        incident_id,
        volunteer.id,
        outcome,
        active_count,
    )
    return AcceptResult(outcome, incident_id, active_count)


async def update_assignment(
    session: AsyncSession,
    line_user_id: str,
    incident_id: int,
    action: AssignmentAction,
    now: datetime,
) -> UpdateResult:
    incident = await session.get(Incident, incident_id, with_for_update=True)
    if incident is None:
        logger.warning("%s for unknown incident: incident_id=%s", action, incident_id)
        return UpdateResult(UpdateOutcome.INCIDENT_NOT_FOUND, incident_id, action)
    if incident.status not in ACTIVE_INCIDENT_STATUSES:
        logger.info(
            "%s on inactive incident: incident_id=%s status=%s line_user_id=%s",
            action,
            incident_id,
            incident.status,
            line_user_id,
        )
        return UpdateResult(UpdateOutcome.INCIDENT_CLOSED, incident_id, action)

    volunteer = await find_volunteer_by_line_user(session, line_user_id)
    assignment = (
        await find_assignment(session, incident_id, volunteer.id)
        if volunteer is not None
        else None
    )
    if assignment is None:
        logger.warning(
            "%s without assignment: incident_id=%s line_user_id=%s",
            action,
            incident_id,
            line_user_id,
        )
        return UpdateResult(UpdateOutcome.NOT_ASSIGNED, incident_id, action)

    if (
        volunteer.status != VolunteerStatus.APPROVED
        and action != AssignmentAction.WITHDRAW
    ):
        logger.warning(
            "%s by non-approved volunteer: incident_id=%s volunteer_id=%s status=%s",
            action,
            incident_id,
            volunteer.id,
            volunteer.status,
        )
        return UpdateResult(
            UpdateOutcome.VOLUNTEER_NOT_APPROVED,
            incident_id,
            action,
            assignment_status=assignment.status,
        )

    allowed_from, target = TRANSITIONS[action]
    if assignment.status == target:
        return await unchanged_result(session, incident_id, action, assignment.status)
    if assignment.status not in allowed_from:
        logger.info(
            "invalid assignment transition: incident_id=%s volunteer_id=%s %s -> %s",
            incident_id,
            volunteer.id,
            assignment.status,
            target,
        )
        return UpdateResult(
            UpdateOutcome.INVALID_TRANSITION,
            incident_id,
            action,
            assignment_status=assignment.status,
        )

    previous = assignment.status
    assignment.status = target
    if target == AssignmentStatus.DONE:
        assignment.completed_at = now
    session.add(
        IncidentEvent(
            incident_id=incident_id,
            event_type=ACTION_EVENTS[action],
            actor_type=ActorType.VOLUNTEER,
            actor_id=line_user_id,
            payload={
                "assignment_id": assignment.id,
                "volunteer_id": volunteer.id,
                "from": previous.value,
                "to": target.value,
            },
            created_at=now,
        )
    )
    await session.flush()

    active_count = await count_assignments(
        session, incident_id, ACTIVE_ASSIGNMENT_STATUSES
    )
    incident_closed = False
    all_withdrawn = False
    if action == AssignmentAction.DONE:
        await close_incident(
            session,
            incident,
            line_user_id,
            now,
            closed_by_volunteer_id=volunteer.id,
            others_on_site=active_count,
        )
        incident_closed = True
    elif action == AssignmentAction.WITHDRAW and active_count == 0:
        await reopen_after_all_withdrawn(session, incident, line_user_id, now)
        all_withdrawn = True
    elif action == AssignmentAction.WITHDRAW:
        await enqueue_assignment_summary(session, incident_id, now)

    logger.info(
        "assignment updated: incident_id=%s volunteer_id=%s %s -> %s active=%s "
        "closed=%s all_withdrawn=%s",
        incident_id,
        volunteer.id,
        previous,
        target,
        active_count,
        incident_closed,
        all_withdrawn,
    )
    return UpdateResult(
        UpdateOutcome.UPDATED,
        incident_id,
        action,
        assignment_status=target,
        active_volunteer_count=active_count,
        incident_closed=incident_closed,
        all_withdrawn=all_withdrawn,
    )


async def unchanged_result(
    session: AsyncSession,
    incident_id: int,
    action: AssignmentAction,
    status: AssignmentStatus,
) -> UpdateResult:
    active_count = await count_assignments(
        session, incident_id, ACTIVE_ASSIGNMENT_STATUSES
    )
    return UpdateResult(
        UpdateOutcome.UNCHANGED,
        incident_id,
        action,
        assignment_status=status,
        active_volunteer_count=active_count,
    )


async def close_incident(
    session: AsyncSession,
    incident: Incident,
    line_user_id: str,
    now: datetime,
    closed_by_volunteer_id: int,
    others_on_site: int,
) -> None:
    incident.status = IncidentStatus.CLOSED
    incident.closed_at = now
    session.add(
        IncidentEvent(
            incident_id=incident.id,
            event_type=EVENT_INCIDENT_CLOSED,
            actor_type=ActorType.VOLUNTEER,
            actor_id=line_user_id,
            payload={
                "reason": "volunteer_marked_done",
                "volunteer_id": closed_by_volunteer_id,
                "others_on_site": others_on_site,
            },
            created_at=now,
        )
    )
    closed_key = now.isoformat()
    await enqueue_job(
        session,
        job_type=JOB_INCIDENT_CLOSED,
        payload={
            "incident_id": incident.id,
            "closed_at": closed_key,
            "closed_by_volunteer_id": closed_by_volunteer_id,
        },
        idempotency_key=f"{JOB_INCIDENT_CLOSED}:{incident.id}:{closed_key}",
    )
    log = logger.warning if others_on_site else logger.info
    log(
        "incident closed: incident_id=%s closed_by_volunteer_id=%s others_on_site=%s",
        incident.id,
        closed_by_volunteer_id,
        others_on_site,
    )


async def reopen_after_all_withdrawn(
    session: AsyncSession,
    incident: Incident,
    line_user_id: str,
    now: datetime,
) -> None:
    incident.status = IncidentStatus.OPEN
    event = IncidentEvent(
        incident_id=incident.id,
        event_type=EVENT_ALL_WITHDRAWN,
        actor_type=ActorType.VOLUNTEER,
        actor_id=line_user_id,
        created_at=now,
    )
    session.add(event)
    await session.flush()

    round_key = f"{DispatchReason.ALL_WITHDRAWN.value}:{event.id}"
    await enqueue_dispatch(
        session,
        incident.id,
        DispatchReason.ALL_WITHDRAWN,
        round_key=round_key,
    )
    await enqueue_escalation_check(
        session, incident.id, now, round_key=round_key, after_event_id=event.id
    )
    await record_admin_alert(
        session,
        alert_type=ALERT_ALL_WITHDRAWN,
        severity=AlertSeverity.CRITICAL,
        message=(
            f"จิตอาสาถอนตัวจากเหตุ #{incident.id} ครบทุกคน ตอนนี้ไม่มีใครไปหน้างาน "
            "ระบบส่งหาจิตอาสาในอำเภออีกรอบแล้ว กรุณาติดตาม"
        ),
        payload={"incident_id": incident.id, "event_id": event.id},
        dedup_key=f"{ALERT_ALL_WITHDRAWN}:{incident.id}",
    )
    logger.error("all volunteers withdrew: incident_id=%s", incident.id)


def summary_window_of(now: datetime) -> int:
    return int(now.timestamp() // SUMMARY_WINDOW.total_seconds())


def summary_window_bounds(window: int) -> tuple[datetime, datetime]:
    seconds = SUMMARY_WINDOW.total_seconds()
    return (
        datetime.fromtimestamp(window * seconds, UTC),
        datetime.fromtimestamp((window + 1) * seconds, UTC),
    )


async def enqueue_assignment_summary(
    session: AsyncSession,
    incident_id: int,
    now: datetime,
) -> bool:
    window = summary_window_of(now)
    _, run_at = summary_window_bounds(window)
    return await enqueue_job(
        session,
        job_type=JOB_ASSIGNMENT_SUMMARY,
        payload={"incident_id": incident_id, "window": window},
        idempotency_key=f"{JOB_ASSIGNMENT_SUMMARY}:{incident_id}:{window}",
        run_at=run_at,
    )


async def find_assignment(
    session: AsyncSession,
    incident_id: int,
    volunteer_id: int,
) -> Assignment | None:
    statement = sa.select(Assignment).where(
        Assignment.incident_id == incident_id,
        Assignment.volunteer_id == volunteer_id,
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def count_assignments(
    session: AsyncSession,
    incident_id: int,
    statuses: tuple[AssignmentStatus, ...],
) -> int:
    statement = sa.select(sa.func.count(Assignment.id)).where(
        Assignment.incident_id == incident_id,
        Assignment.status.in_(statuses),
    )
    return (await session.execute(statement)).scalar_one()
