import pytest
from linebot.v3.messaging.api_client import ApiException

from line.line_service import LineService

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def service() -> LineService:
    line = LineService.__new__(LineService)
    line.max_retries = 3
    line.backoff_factor = 0
    return line


class Operation:
    def __init__(self, *errors: Exception):
        self.errors = list(errors)
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "sent"


async def test_conflict_on_first_attempt_with_caller_key_means_already_sent():
    operation = Operation(ApiException(status=409))

    result = await service().retry(
        operation, caller_retry_key=True, x_line_retry_key="stable-key"
    )

    assert result is None
    assert operation.calls == 1


async def test_conflict_on_first_attempt_with_random_key_raises():
    operation = Operation(ApiException(status=409))

    with pytest.raises(ApiException):
        await service().retry(operation, x_line_retry_key="random-key")


async def test_conflict_after_retry_means_already_sent():
    operation = Operation(ApiException(status=500), ApiException(status=409))

    result = await service().retry(operation, x_line_retry_key="random-key")

    assert result is None
    assert operation.calls == 2


async def test_conflict_without_retry_key_raises():
    operation = Operation(ApiException(status=500), ApiException(status=409))

    with pytest.raises(ApiException):
        await service().retry(operation)
