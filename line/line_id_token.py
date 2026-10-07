import logging
from dataclasses import dataclass

import httpx

from config.config import settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
VERIFY_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class LineIdentity:
    user_id: str
    display_name: str | None


class InvalidIdTokenError(Exception):
    pass


class IdTokenVerificationUnavailableError(Exception):
    pass


async def verify_id_token(id_token: str) -> LineIdentity:
    try:
        async with httpx.AsyncClient(timeout=VERIFY_TIMEOUT_SECONDS) as client:
            response = await client.post(
                VERIFY_URL,
                data={"id_token": id_token, "client_id": settings.LINE_LOGIN_CHANNEL_ID},
            )
    except httpx.HTTPError as error:
        raise IdTokenVerificationUnavailableError(type(error).__name__) from error

    if response.status_code == 400:
        raise InvalidIdTokenError(response.text[:200])
    if response.status_code != 200:
        raise IdTokenVerificationUnavailableError(f"status={response.status_code}")

    try:
        claims = response.json()
    except ValueError as error:
        raise IdTokenVerificationUnavailableError("invalid JSON response") from error

    if claims.get("aud") != settings.LINE_LOGIN_CHANNEL_ID:
        raise InvalidIdTokenError("audience mismatch")

    user_id = claims.get("sub")
    if not user_id:
        raise InvalidIdTokenError("missing sub claim")

    return LineIdentity(user_id=user_id, display_name=claims.get("name"))
