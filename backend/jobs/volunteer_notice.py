import logging
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.common import push_message
from line.line_flex import build_volunteer_status_notice
from models import VolunteerStatus
from services.jobs import PermanentJobError
from services.volunteers import load_volunteer_notice

logger = logging.getLogger(__name__)


async def handle_volunteer_status_notice(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    volunteer_id = payload.get("volunteer_id")
    changed_at = payload.get("changed_at")
    if not isinstance(volunteer_id, int):
        raise PermanentJobError(f"invalid volunteer_id in payload: {payload!r}")
    try:
        status = VolunteerStatus(payload.get("status"))
    except ValueError as error:
        raise PermanentJobError(f"invalid status in payload: {payload!r}") from error

    async with sessionmaker() as session:
        notice = await load_volunteer_notice(session, volunteer_id)
    if notice is None:
        raise PermanentJobError(f"volunteer not found: {volunteer_id}")

    if notice.status != status:
        logger.info(
            "skip volunteer status notice, superseded: id=%s notice=%s current=%s",
            volunteer_id,
            status,
            notice.status,
        )
        return

    message = build_volunteer_status_notice(status, notice.district_name)
    if message is None:
        raise PermanentJobError(f"no notice message for status: {status}")

    await push_message(
        notice.line_user_id,
        message,
        key_prefix=("volunteer_status", volunteer_id, status.value, changed_at),
    )
    logger.info(
        "volunteer status notified: id=%s status=%s", volunteer_id, status
    )
