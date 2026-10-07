import logging
import uuid
from typing import Any

from linebot.v3.webhooks import Event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from line.line_handler import handle_event
from services.jobs import PermanentJobError, enqueue_job

logger = logging.getLogger(__name__)

JOB_LINE_EVENT = "line_event"


async def enqueue_line_event(session: AsyncSession, raw_event: dict[str, Any]) -> bool:
    webhook_event_id = raw_event.get("webhookEventId")
    if not webhook_event_id:
        webhook_event_id = f"missing:{uuid.uuid4()}"
        logger.warning(
            "LINE event without webhookEventId, cannot dedup: type=%s",
            raw_event.get("type"),
        )
    return await enqueue_job(
        session,
        job_type=JOB_LINE_EVENT,
        payload={"event": raw_event},
        idempotency_key=f"{JOB_LINE_EVENT}:{webhook_event_id}",
    )


async def handle_line_event(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    raw_event = payload.get("event")
    if not isinstance(raw_event, dict):
        raise PermanentJobError(f"invalid LINE event payload: {payload!r}")
    try:
        event = Event.from_dict(raw_event)
    except ValueError:
        logger.warning(
            "unsupported LINE event type, skipped: type=%s webhook_event_id=%s",
            raw_event.get("type"),
            raw_event.get("webhookEventId"),
        )
        return
    await handle_event(event)
