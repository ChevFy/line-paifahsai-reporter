import logging
from dataclasses import dataclass

import httpx

from config.config import settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
VERIFY_TIMEOUT_SECONDS = 5.0
AUDIENCE_ERROR_MARKER = "audience"

_http_client: httpx.AsyncClient | None = None


@dataclass(frozen=True)
class LineIdentity:
    user_id: str
    display_name: str | None


class InvalidIdTokenError(Exception):
    pass


class IdTokenVerificationUnavailableError(Exception):
    pass


class IdTokenConfigError(IdTokenVerificationUnavailableError):
    pass


def get_http_client() -> httpx.AsyncClient:
    global _http_client

    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=VERIFY_TIMEOUT_SECONDS)
    return _http_client


async def close_id_token_client() -> None:
    global _http_client

    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def verify_id_token(id_token: str) -> LineIdentity:
    try:
        response = await get_http_client().post(
            VERIFY_URL,
            data={"id_token": id_token, "client_id": settings.LINE_LOGIN_CHANNEL_ID},
        )
    except httpx.HTTPError as error:
        raise IdTokenVerificationUnavailableError(type(error).__name__) from error

    if response.status_code == 400:
        error_description = read_error_description(response)
        if AUDIENCE_ERROR_MARKER in error_description.lower():
            raise IdTokenConfigError(error_description)
        raise InvalidIdTokenError(error_description or response.text[:200])
    if response.status_code != 200:
        raise IdTokenVerificationUnavailableError(f"status={response.status_code}")

    try:
        claims = response.json()
    except ValueError as error:
        raise IdTokenVerificationUnavailableError("invalid JSON response") from error

    if claims.get("aud") != settings.LINE_LOGIN_CHANNEL_ID:
        raise IdTokenConfigError(f"audience mismatch: aud={claims.get('aud')}")

    user_id = claims.get("sub")
    if not user_id:
        raise InvalidIdTokenError("missing sub claim")

    return LineIdentity(user_id=user_id, display_name=claims.get("name"))


def read_error_description(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    return str(body.get("error_description") or "")[:200]
