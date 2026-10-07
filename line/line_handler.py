import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from linebot.v3.messaging import Message, TextMessage
from linebot.v3.webhooks import Event, MessageEvent, PostbackEvent, TextMessageContent

from config.config import settings
from core.alerts import record_admin_alert_safely
from core.db import SessionLocal
from line.line_client import get_line_service
from line.line_flex import ACTION_ACCEPT, parse_postback_data
from models import AlertSeverity
from services.assignments import AcceptOutcome, AcceptResult, accept_incident

logger = logging.getLogger(__name__)

MAX_ERROR_TEXT_LENGTH = 500
EVENT_FAILED_ALERT_TYPE = "line_event_failed"
STALE_BUTTON_MESSAGE = "ปุ่มนี้ใช้ไม่ได้แล้ว กรุณาใช้ข้อความแจ้งเหตุล่าสุด"
PUSH_RETRY_KEY_NAMESPACE = uuid.UUID("2b0f6c1e-8d4a-4f3b-9e2c-5a7d1b3c4e6f")


async def handle_event(event: Event) -> None:
    try:
        if isinstance(event, MessageEvent) and isinstance(
            event.message, TextMessageContent
        ):
            await handle_text_message(event)
        elif isinstance(event, PostbackEvent):
            await handle_postback(event)
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

    await record_admin_alert_safely(
        alert_type=EVENT_FAILED_ALERT_TYPE,
        severity=AlertSeverity.CRITICAL,
        message=message,
        payload=payload,
        dedup_key=f"{EVENT_FAILED_ALERT_TYPE}:{event.webhook_event_id}",
    )
    await send_debug_alert_to_line(event, message)


async def send_debug_alert_to_line(event: Event, message: str) -> None:
    admin_user_ids = settings.ADMIN_LINE_USER_IDS
    if not admin_user_ids:
        return

    try:
        await get_line_service().multicast(admin_user_ids, TextMessage(text=message))
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


def accept_reply_text(result: AcceptResult) -> str:
    incident = f"เหตุ #{result.incident_id}"
    match result.outcome:
        case AcceptOutcome.ACCEPTED | AcceptOutcome.REJOINED:
            return (
                f"รับ{incident}แล้ว ขอบคุณครับ "
                f"ตอนนี้มีจิตอาสารับงานนี้ {result.active_volunteer_count} คน\n"
                "เดินทางปลอดภัย หากไฟลุกลามเกินกำลังโทร 1362"
            )
        case AcceptOutcome.ALREADY_ACCEPTED:
            return (
                f"คุณรับ{incident}ไว้แล้ว "
                f"มีจิตอาสารับงานนี้ {result.active_volunteer_count} คน"
            )
        case AcceptOutcome.NOT_VOLUNTEER:
            return "บัญชีนี้ยังไม่ได้รับอนุมัติเป็นจิตอาสา จึงรับงานไม่ได้"
        case AcceptOutcome.INCIDENT_CLOSED:
            return f"{incident}ปิดไปแล้ว ไม่ต้องออกไป ขอบคุณครับ"
        case AcceptOutcome.INCIDENT_NOT_FOUND:
            return STALE_BUTTON_MESSAGE


async def handle_postback(event: PostbackEvent) -> None:
    user_id = get_user_id(event)
    parsed = parse_postback_data(event.postback.data)
    if user_id is None or parsed is None:
        logger.warning(
            "unrecognized postback: webhook_event_id=%s user_id=%s data=%r",
            event.webhook_event_id,
            user_id,
            event.postback.data,
        )
        await respond(event, TextMessage(text=STALE_BUTTON_MESSAGE))
        return

    action, incident_id = parsed
    if action == ACTION_ACCEPT:
        async with SessionLocal() as session, session.begin():
            result = await accept_incident(
                session, user_id, incident_id, datetime.now(UTC)
            )
        await respond(event, TextMessage(text=accept_reply_text(result)))


async def respond(event: MessageEvent | PostbackEvent, message: Message) -> None:
    try:
        await reply_message(event.reply_token, message)
        return
    except Exception:
        logger.warning(
            "reply failed, falling back to push: webhook_event_id=%s",
            event.webhook_event_id,
            exc_info=True,
        )

    user_id = get_user_id(event)
    if user_id is None:
        raise RuntimeError("reply failed and event has no user_id to push to")
    retry_key = str(uuid.uuid5(PUSH_RETRY_KEY_NAMESPACE, event.webhook_event_id))
    await push_message(user_id, message, retry_key=retry_key)


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
