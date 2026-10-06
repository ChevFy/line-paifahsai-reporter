from functools import partial

import httpx
import pytest

from line import line_id_token
from line.line_id_token import (
    IdTokenVerificationUnavailableError,
    InvalidIdTokenError,
    verify_id_token,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def use_transport(monkeypatch, handler):
    monkeypatch.setattr(
        line_id_token.httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )


async def test_valid_token_returns_identity(monkeypatch):
    use_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"sub": "U123", "name": "Somchai", "aud": "test-login-channel"}
        ),
    )
    identity = await verify_id_token("token")
    assert identity.user_id == "U123"
    assert identity.display_name == "Somchai"


async def test_rejected_token_raises_invalid(monkeypatch):
    use_transport(monkeypatch, lambda request: httpx.Response(400, json={"error": "x"}))
    with pytest.raises(InvalidIdTokenError):
        await verify_id_token("token")


async def test_audience_mismatch_raises_invalid(monkeypatch):
    use_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={"sub": "U123", "aud": "other"}),
    )
    with pytest.raises(InvalidIdTokenError):
        await verify_id_token("token")


async def test_line_server_error_raises_unavailable(monkeypatch):
    use_transport(monkeypatch, lambda request: httpx.Response(500))
    with pytest.raises(IdTokenVerificationUnavailableError):
        await verify_id_token("token")


async def test_network_error_raises_unavailable(monkeypatch):
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    use_transport(monkeypatch, handler)
    with pytest.raises(IdTokenVerificationUnavailableError):
        await verify_id_token("token")
