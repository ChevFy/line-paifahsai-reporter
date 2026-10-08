import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    Configuration,
    Message,
    MulticastRequest,
    PushMessageRequest,
    ReplyMessageRequest,
)
from linebot.v3.messaging.api_client import ApiException

logger = logging.getLogger(__name__)
T = TypeVar("T")


class LineService:
    def __init__(
        self,
        config: Configuration,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if backoff_factor < 0:
            raise ValueError("backoff_factor must not be negative")

        self.config = config
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.api_client = AsyncApiClient(configuration=self.config)
        self.api = AsyncMessagingApi(self.api_client)
        self.blob_api = AsyncMessagingApiBlob(self.api_client)

    async def retry(
        self,
        operation: Callable[..., Awaitable[T]],
        *args,
        caller_retry_key: bool = False,
        **kwargs,
    ) -> T | None:
        operation_name = getattr(operation, "__name__", repr(operation))

        for attempt in range(self.max_retries):
            try:
                return await operation(*args, **kwargs)
            except Exception as error:
                if self._already_accepted(error, attempt, caller_retry_key, kwargs):
                    log = logger.warning if attempt == 0 else logger.info
                    log(
                        "LINE API request already accepted earlier, not resent: %s "
                        "attempt=%s caller_retry_key=%s retry_key=%s",
                        operation_name,
                        attempt,
                        caller_retry_key,
                        kwargs.get("x_line_retry_key"),
                    )
                    return None
                if not self._is_retryable(error) or attempt == self.max_retries - 1:
                    logger.exception("LINE API request failed: %s", operation_name)
                    raise

                delay = self.backoff_factor * (2**attempt)
                logger.warning(
                    "LINE API request failed, retrying %s/%s in %.2fs: %s",
                    attempt + 1,
                    self.max_retries - 1,
                    delay,
                    operation_name,
                )
                await asyncio.sleep(delay)

        raise RuntimeError("retry loop exited unexpectedly")

    @classmethod
    def _already_accepted(
        cls,
        error: Exception,
        attempt: int,
        caller_retry_key: bool,
        kwargs: dict,
    ) -> bool:
        if "x_line_retry_key" not in kwargs or not cls._is_conflict(error):
            return False
        return attempt > 0 or caller_retry_key

    @staticmethod
    def _is_conflict(error: Exception) -> bool:
        return isinstance(error, ApiException) and error.status == 409

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        if isinstance(error, (asyncio.TimeoutError, OSError)):
            return True
        if isinstance(error, ApiException):
            status = error.status
            return status in {408, 429} or status is not None and status >= 500
        return False

    async def reply(self, reply_token: str, messages: Message | Sequence[Message]):
        request = ReplyMessageRequest(
            reply_token=reply_token,
            messages=self._as_message_list(messages),
        )
        return await self.retry(self.api.reply_message, request)

    async def push(
        self,
        to: str,
        messages: Message | Sequence[Message],
        retry_key: str | None = None,
    ):
        request = PushMessageRequest(to=to, messages=self._as_message_list(messages))
        return await self.retry(
            self.api.push_message,
            request,
            caller_retry_key=retry_key is not None,
            x_line_retry_key=retry_key or str(uuid.uuid4()),
        )

    async def multicast(
        self,
        to: Sequence[str],
        messages: Message | Sequence[Message],
        retry_key: str | None = None,
    ):
        request = MulticastRequest(
            to=list(to),
            messages=self._as_message_list(messages),
        )
        return await self.retry(
            self.api.multicast,
            request,
            caller_retry_key=retry_key is not None,
            x_line_retry_key=retry_key or str(uuid.uuid4()),
        )

    async def get_profile(self, user_id: str):
        return await self.retry(self.api.get_profile, user_id)

    async def get_content(self, message_id: str) -> bytearray:
        return await self.retry(self.blob_api.get_message_content, message_id)

    @staticmethod
    def _as_message_list(messages: Message | Sequence[Message]) -> list[Message]:
        if isinstance(messages, Message):
            return [messages]
        return list(messages)

    async def close(self) -> None:
        await self.api_client.close()
