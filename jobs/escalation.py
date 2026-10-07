import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.common import require_incident_id
from services.escalation import escalate_if_unaccepted
from services.jobs import PermanentJobError

logger = logging.getLogger(__name__)


async def handle_escalate_incident(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    incident_id = require_incident_id(payload)
    async with sessionmaker() as session, session.begin():
        try:
            outcome = await escalate_if_unaccepted(
                session, incident_id, datetime.now(UTC)
            )
        except LookupError as error:
            raise PermanentJobError(str(error)) from error
    logger.info("escalation check done: incident_id=%s outcome=%s", incident_id, outcome)
