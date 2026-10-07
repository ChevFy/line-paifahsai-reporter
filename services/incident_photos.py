import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from urllib.parse import urlencode

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import Report

PHOTO_LINK_TTL = timedelta(days=3)


class LinkStatus(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass(frozen=True)
class IncidentPhoto:
    report_id: int
    created_at: datetime


def sign_incident_link(secret: str, incident_id: int, expires: int) -> str:
    message = f"incident-photos:{incident_id}:{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def link_query(secret: str, incident_id: int, expires: int) -> str:
    signature = sign_incident_link(secret, incident_id, expires)
    return urlencode({"expires": expires, "sig": signature})


def build_photo_page_url(
    base_url: str,
    secret: str,
    incident_id: int,
    now: datetime,
) -> str:
    expires = int((now + PHOTO_LINK_TTL).timestamp())
    query = link_query(secret, incident_id, expires)
    return f"{base_url.rstrip('/')}/incidents/{incident_id}/photos?{query}"


def verify_incident_link(
    secret: str,
    incident_id: int,
    expires: int,
    signature: str,
    now: datetime,
) -> LinkStatus:
    expected = sign_incident_link(secret, incident_id, expires)
    if not hmac.compare_digest(expected, signature):
        return LinkStatus.INVALID
    if expires < now.timestamp():
        return LinkStatus.EXPIRED
    return LinkStatus.VALID


async def list_incident_photos(
    session: AsyncSession,
    incident_id: int,
) -> list[IncidentPhoto]:
    rows = await session.execute(
        sa.select(Report.id, Report.created_at)
        .where(Report.incident_id == incident_id, Report.image_path.is_not(None))
        .order_by(Report.created_at, Report.id)
    )
    return [IncidentPhoto(row.id, row.created_at) for row in rows]


async def find_incident_photo_key(
    session: AsyncSession,
    incident_id: int,
    report_id: int,
) -> str | None:
    return (
        await session.execute(
            sa.select(Report.image_path).where(
                Report.id == report_id,
                Report.incident_id == incident_id,
            )
        )
    ).scalar_one_or_none()
