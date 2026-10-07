import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from line.line_client import get_line_service
from line.line_flex import build_incident_alert
from services.dispatch import (
    load_dispatch_target,
    record_dispatched,
    record_no_volunteers,
)
from services.jobs import PermanentJobError

logger = logging.getLogger(__name__)

MULTICAST_LIMIT = 500
RETRY_KEY_NAMESPACE = uuid.UUID("6f1d2b8e-3c4a-4e5f-9a7b-1c2d3e4f5a6b")


def dispatch_retry_key(incident_id: int, chunk_index: int) -> str:
    return str(uuid.uuid5(RETRY_KEY_NAMESPACE, f"dispatch:{incident_id}:{chunk_index}"))


async def handle_dispatch_incident(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    incident_id = payload.get("incident_id")
    if not isinstance(incident_id, int):
        raise PermanentJobError(f"invalid incident_id in payload: {payload!r}")

    async with sessionmaker() as session:
        try:
            target = await load_dispatch_target(session, incident_id)
        except LookupError as error:
            raise PermanentJobError(str(error)) from error

    if target is None:
        return

    if not target.recipients:
        async with sessionmaker() as session, session.begin():
            await record_no_volunteers(session, target)
        return

    message = build_incident_alert(target)
    line = get_line_service()
    for start in range(0, len(target.recipients), MULTICAST_LIMIT):
        chunk = target.recipients[start : start + MULTICAST_LIMIT]
        chunk_index = start // MULTICAST_LIMIT
        await line.multicast(
            chunk,
            message,
            retry_key=dispatch_retry_key(incident_id, chunk_index),
        )
        logger.info(
            "dispatch multicast sent: incident_id=%s chunk=%s recipients=%s",
            incident_id,
            chunk_index,
            len(chunk),
        )

    async with sessionmaker() as session, session.begin():
        await record_dispatched(session, target)
