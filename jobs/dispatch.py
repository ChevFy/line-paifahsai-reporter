import logging
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.common import multicast_in_chunks, require_incident_id
from line.line_flex import build_incident_alert
from services.dispatch import (
    DispatchReason,
    load_dispatch_target,
    record_dispatched,
    record_no_volunteers,
)
from services.jobs import PermanentJobError

logger = logging.getLogger(__name__)


async def handle_dispatch_incident(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    incident_id = require_incident_id(payload)
    try:
        reason = DispatchReason(payload.get("reason", DispatchReason.INITIAL.value))
    except ValueError as error:
        raise PermanentJobError(f"invalid dispatch reason: {payload!r}") from error
    round_key = payload.get("round", reason.value)

    async with sessionmaker() as session:
        try:
            target = await load_dispatch_target(session, incident_id, reason)
        except LookupError as error:
            raise PermanentJobError(str(error)) from error

    if target is None:
        return

    if not target.recipients:
        async with sessionmaker() as session, session.begin():
            await record_no_volunteers(session, target)
        return

    await multicast_in_chunks(
        target.recipients,
        build_incident_alert(target),
        key_prefix=("dispatch", incident_id, round_key),
    )

    async with sessionmaker() as session, session.begin():
        await record_dispatched(session, target)
