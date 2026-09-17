import logging

from linebot.v3.messaging import ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from line.line_client import get_line_bot_api

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

    await get_line_bot_api().reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=text)],
        )
    )
