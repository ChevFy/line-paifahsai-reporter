import logging
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.common import multicast_in_chunks, require_incident_id
from line.line_flex import (
    build_assignment_summary,
    build_closure_for_reporter,
    build_closure_for_volunteer,
)
from services.jobs import PermanentJobError
from services.notifications import load_assignment_summary, load_closure_notice

logger = logging.getLogger(__name__)


async def handle_assignment_summary(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    incident_id = require_incident_id(payload)
    window = payload.get("window")

    async with sessionmaker() as session:
        try:
            summary = await load_assignment_summary(session, incident_id)
        except LookupError as error:
            raise PermanentJobError(str(error)) from error

    if summary is None:
        logger.info("skip assignment summary, incident inactive: id=%s", incident_id)
        return
    if not summary.recipients:
        logger.warning("assignment summary has no recipients: id=%s", incident_id)
        return

    await multicast_in_chunks(
        summary.recipients,
        build_assignment_summary(summary),
        key_prefix=("summary", incident_id, window),
    )
    logger.info(
        "assignment summary sent: incident_id=%s volunteers=%s recipients=%s",
        incident_id,
        len(summary.volunteer_names),
        len(summary.recipients),
    )


async def handle_incident_closed(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    incident_id = require_incident_id(payload)
    closed_at = payload.get("closed_at")

    async with sessionmaker() as session:
        try:
            notice = await load_closure_notice(session, incident_id)
        except LookupError as error:
            raise PermanentJobError(str(error)) from error

    await multicast_in_chunks(
        notice.reporter_ids,
        build_closure_for_reporter(incident_id, notice.district_name),
        key_prefix=("closed", incident_id, closed_at, "reporters"),
    )
    await multicast_in_chunks(
        notice.volunteer_ids,
        build_closure_for_volunteer(incident_id, notice.district_name),
        key_prefix=("closed", incident_id, closed_at, "volunteers"),
    )
    logger.info(
        "incident closure notified: incident_id=%s reporters=%s volunteers=%s",
        incident_id,
        len(notice.reporter_ids),
        len(notice.volunteer_ids),
    )
