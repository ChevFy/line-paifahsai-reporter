from linebot.v3.messaging import Configuration

from config.config import settings
from line.line_service import LineService

configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)

_line_service: LineService | None = None


def get_line_service() -> LineService:
    global _line_service

    if _line_service is None:
        _line_service = LineService(configuration)
    return _line_service


async def close_line_bot_api() -> None:
    global _line_service

    if _line_service is not None:
        await _line_service.close()
        _line_service = None
