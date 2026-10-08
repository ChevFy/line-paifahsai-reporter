import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ACTIVE_INCIDENT_STATUSES,
    Assignment,
    Incident,
    IncidentEvent,
    Report,
    Volunteer,
)
from services.assignments import ACTIVE_ASSIGNMENT_STATUSES
from services.dispatch import EVENT_DISPATCHED
from services.jobs import enqueue_job
from services.volunteers import approved_line_user_ids_in_district

logger = logging.getLogger(__name__)

JOB_SEND_INCIDENT_PHOTO = "send_incident_photo"


@dataclass(frozen=True)
class PhotoDelivery:
    incident_id: int
    incident_public_id: uuid.UUID
    report_id: int
    image_path: str
    recipients: list[str]


async def enqueue_photo_delivery(session: AsyncSession, incident_id: int) -> bool:
    return await enqueue_job(
        session,
        job_type=JOB_SEND_INCIDENT_PHOTO,
        payload={"incident_id": incident_id},
        idempotency_key=f"{JOB_SEND_INCIDENT_PHOTO}:{incident_id}",
    )


async def has_photo(session: AsyncSession, incident_id: int) -> bool:
    statement = sa.select(
        sa.exists().where(
            Report.incident_id == incident_id, Report.image_path.is_not(None)
        )
    )
    return (await session.execute(statement)).scalar_one()


async def was_dispatched(session: AsyncSession, incident_id: int) -> bool:
    statement = sa.select(
        sa.exists().where(
            IncidentEvent.incident_id == incident_id,
            IncidentEvent.event_type == EVENT_DISPATCHED,
        )
    )
    return (await session.execute(statement)).scalar_one()


async def schedule_photo_after_dispatch(
    session: AsyncSession, incident_id: int
) -> bool:
    if not await has_photo(session, incident_id):
        logger.info("no photo yet at dispatch: incident_id=%s", incident_id)
        return False
    return await enqueue_photo_delivery(session, incident_id)


async def schedule_photo_after_upload(
    session: AsyncSession, incident_id: int | None
) -> bool:
    if incident_id is None:
        logger.warning("photo attached to report without incident")
        return False
    incident = await session.get(Incident, incident_id, with_for_update=True)
    if incident is None or incident.status not in ACTIVE_INCIDENT_STATUSES:
        logger.info(
            "photo not delivered, incident inactive: incident_id=%s", incident_id
        )
        return False
    if not await was_dispatched(session, incident_id):
        logger.info(
            "photo waits for dispatch to deliver it: incident_id=%s", incident_id
        )
        return False
    return await enqueue_photo_delivery(session, incident_id)


async def load_photo_delivery(
    session: AsyncSession, incident_id: int
) -> PhotoDelivery | None:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise LookupError(f"incident {incident_id} not found")
    if incident.status not in ACTIVE_INCIDENT_STATUSES:
        return None

    photo = (
        await session.execute(
            sa.select(Report.id, Report.image_path)
            .where(Report.incident_id == incident_id, Report.image_path.is_not(None))
            .order_by(Report.created_at, Report.id)
            .limit(1)
        )
    ).one_or_none()
    if photo is None:
        raise LookupError(f"incident {incident_id} has no photo")

    recipients = await approved_line_user_ids_in_district(
        session, incident.district_code
    )
    assignees = (
        await session.execute(
            sa.select(Volunteer.line_user_id)
            .join(Assignment, Assignment.volunteer_id == Volunteer.id)
            .where(
                Assignment.incident_id == incident_id,
                Assignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            )
            .order_by(Assignment.id)
        )
    ).scalars()
    for line_user_id in assignees:
        if line_user_id not in recipients:
            recipients.append(line_user_id)

    return PhotoDelivery(
        incident_id=incident_id,
        incident_public_id=incident.public_id,
        report_id=photo.id,
        image_path=photo.image_path,
        recipients=recipients,
    )
