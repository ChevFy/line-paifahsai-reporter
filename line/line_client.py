from linebot.v3.messaging import AsyncApiClient, AsyncMessagingApi, Configuration

from config.config import settings

configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)

_api_client: AsyncApiClient | None = None
_messaging_api: AsyncMessagingApi | None = None


def get_line_bot_api() -> AsyncMessagingApi:
    global _api_client, _messaging_api

    if _messaging_api is None:
        _api_client = AsyncApiClient(configuration)
        _messaging_api = AsyncMessagingApi(_api_client)
    return _messaging_api


async def close_line_bot_api() -> None:
    global _api_client, _messaging_api

    if _api_client is not None:
        await _api_client.close()
        _api_client = None
        _messaging_api = None
