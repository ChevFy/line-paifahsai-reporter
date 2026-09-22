import logging
from collections.abc import Mapping, Sequence

from linebot.v3.messaging import Message, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from line.line_client import get_line_service

logger = logging.getLogger(__name__)


async def handle_event(event) -> None:
    try:
        if isinstance(event, MessageEvent) and isinstance(
            event.message, TextMessageContent
        ):
            await handle_text_message(event)
    except Exception:
        logger.exception("failed to handle event: %s", type(event).__name__)


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
