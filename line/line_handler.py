import logging
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from linebot.v3.messaging import Message, TextMessage
from linebot.v3.webhooks import Event, MessageEvent, TextMessageContent

from config.config import settings
from core.db import SessionLocal
from line.line_client import get_line_service
from models import AlertSeverity
from services.admin_alerts import record_admin_alert

logger = logging.getLogger(__name__)

MAX_ERROR_TEXT_LENGTH = 500
EVENT_FAILED_ALERT_TYPE = "line_event_failed"


async def handle_event(event: Event) -> None:
    try:
        if isinstance(event, MessageEvent) and isinstance(
            event.message, TextMessageContent
        ):
            await handle_text_message(event)
    except Exception as error:
        logger.exception(
            "failed to handle event: type=%s webhook_event_id=%s user_id=%s",
            type(event).__name__,
            event.webhook_event_id,
            get_user_id(event),
        )
        await alert_admins_event_failed(event, error)


def get_user_id(event: Event) -> str | None:
    return getattr(event.source, "user_id", None)


async def alert_admins_event_failed(event: Event, error: Exception) -> None:
    error_text = f"{type(error).__name__}: {error}"[:MAX_ERROR_TEXT_LENGTH]
    payload = {
        "event_type": type(event).__name__,
        "webhook_event_id": event.webhook_event_id,
        "user_id": get_user_id(event),
        "error_type": type(error).__name__,
        "error": error_text,
    }
    message = (
        "ระบบประมวลผล LINE event ไม่สำเร็จ\n"
        f"event: {payload['event_type']}\n"
        f"webhookEventId: {payload['webhook_event_id']}\n"
        f"user_id: {payload['user_id']}\n"
        f"error: {error_text}"
    )

    await record_event_failed_alert(event, message, payload)

    if settings.ADMIN_LINE_USER_IDS:
        await send_debug_alert_to_line(event, message)


async def record_event_failed_alert(
    event: Event,
    message: str,
    payload: dict[str, Any],
) -> None:
    try:
        async with SessionLocal() as session:
            await record_admin_alert(
                session,
                alert_type=EVENT_FAILED_ALERT_TYPE,
                severity=AlertSeverity.CRITICAL,
                message=message,
                payload=payload,
                dedup_key=f"{EVENT_FAILED_ALERT_TYPE}:{event.webhook_event_id}",
            )
    except Exception:
        logger.critical(
            "failed to record admin alert: webhook_event_id=%s",
            event.webhook_event_id,
            exc_info=True,
        )


async def send_debug_alert_to_line(event: Event, message: str) -> None:
    try:
        await get_line_service().multicast(
            settings.ADMIN_LINE_USER_IDS,
            TextMessage(text=message),
            retry_key=str(uuid.uuid4()),
        )
    except Exception:
        logger.error(
            "failed to send debug admin alert to LINE: webhook_event_id=%s",
            event.webhook_event_id,
            exc_info=True,
        )


async def handle_text_message(event: MessageEvent) -> None:
    text = event.message.text

    await reply_message(
        reply_token=event.reply_token,
        messages=TextMessage(text=text),
    )


async def reply_message(reply_token: str, messages: Message | Sequence[Message]):
    return await get_line_service().reply(reply_token, messages)


async def push_message(
    user_id: str,
    messages: Message | Sequence[Message],
    retry_key: str | None = None,
):
    return await get_line_service().push(user_id, messages, retry_key=retry_key)


async def multicast_by_role(
    role: str,
    recipients_by_role: Mapping[str, Sequence[str]],
    messages: Message | Sequence[Message],
    retry_key: str | None = None,
):
    recipients = recipients_by_role.get(role)
    if recipients is None:
        raise ValueError(f"unknown LINE recipient role: {role}")
    if not recipients:
        logger.info("skip multicast: no recipients for role=%s", role)
        return None

    return await get_line_service().multicast(
        recipients,
        messages,
        retry_key=retry_key,
    )


async def get_content(message_id: str) -> bytearray:
    return await get_line_service().get_content(message_id)
