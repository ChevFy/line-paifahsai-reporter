import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.common import require_incident_id
from services.dispatch import DispatchReason
from services.escalation import escalate_if_unaccepted
from services.jobs import PermanentJobError

logger = logging.getLogger(__name__)


async def handle_escalate_incident(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    incident_id = require_incident_id(payload)
    round_key = payload.get("round", DispatchReason.INITIAL.value)
    after_event_id = payload.get("after_event_id", 0)
    if not isinstance(round_key, str) or not isinstance(after_event_id, int):
        raise PermanentJobError(f"invalid escalation payload: {payload!r}")
    async with sessionmaker() as session, session.begin():
        try:
            outcome = await escalate_if_unaccepted(
                session,
                incident_id,
                datetime.now(UTC),
                round_key=round_key,
                after_event_id=after_event_id,
            )
        except LookupError as error:
            raise PermanentJobError(str(error)) from error
    logger.info(
        "escalation check done: incident_id=%s round=%s outcome=%s",
        incident_id,
        round_key,
        outcome,
    )
