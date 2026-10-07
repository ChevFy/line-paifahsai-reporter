import logging
import uuid
from collections.abc import Sequence
from typing import Any

from linebot.v3.messaging import Message

from line.line_client import get_line_service
from services.jobs import PermanentJobError

logger = logging.getLogger(__name__)

MULTICAST_LIMIT = 500
RETRY_KEY_NAMESPACE = uuid.UUID("6f1d2b8e-3c4a-4e5f-9a7b-1c2d3e4f5a6b")


def retry_key(*parts: object) -> str:
    return str(uuid.uuid5(RETRY_KEY_NAMESPACE, ":".join(str(part) for part in parts)))


def require_incident_id(payload: dict[str, Any]) -> int:
    incident_id = payload.get("incident_id")
    if not isinstance(incident_id, int):
        raise PermanentJobError(f"invalid incident_id in payload: {payload!r}")
    return incident_id


async def multicast_in_chunks(
    recipients: Sequence[str],
    message: Message,
    key_prefix: tuple[object, ...],
) -> None:
    line = get_line_service()
    for start in range(0, len(recipients), MULTICAST_LIMIT):
        chunk = recipients[start : start + MULTICAST_LIMIT]
        chunk_index = start // MULTICAST_LIMIT
        await line.multicast(chunk, message, retry_key=retry_key(*key_prefix, chunk_index))
        logger.info(
            "multicast sent: key=%s chunk=%s recipients=%s",
            ":".join(str(part) for part in key_prefix),
            chunk_index,
            len(chunk),
        )
