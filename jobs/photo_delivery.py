import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from config.config import settings
from core.storage import StorageObjectNotFoundError, get_object, put_object
from jobs.common import multicast_in_chunks, require_incident_id
from line.line_flex import build_incident_photo
from services.incident_photos import build_photo_url
from services.jobs import PermanentJobError
from services.photo_delivery import load_photo_delivery
from services.photo_renditions import (
    PhotoVariant,
    UnreadableImageError,
    render_line_images,
    rendition_key,
)

logger = logging.getLogger(__name__)


async def handle_send_incident_photo(
    payload: dict[str, Any],
    sessionmaker: async_sessionmaker,
) -> None:
    incident_id = require_incident_id(payload)

    async with sessionmaker() as session:
        try:
            delivery = await load_photo_delivery(session, incident_id)
        except LookupError as error:
            raise PermanentJobError(str(error)) from error

    if delivery is None:
        logger.info("skip incident photo, incident inactive: id=%s", incident_id)
        return
    if not delivery.recipients:
        logger.warning("incident photo has no recipients: id=%s", incident_id)
        return

    try:
        original, _ = await get_object(delivery.image_path)
    except StorageObjectNotFoundError as error:
        raise PermanentJobError(f"photo missing in storage: {error}") from error

    try:
        renditions = await asyncio.to_thread(render_line_images, original)
    except UnreadableImageError as error:
        raise PermanentJobError(
            f"cannot convert photo for LINE: report_id={delivery.report_id} {error}"
        ) from error

    await put_object(
        rendition_key(delivery.image_path, PhotoVariant.FULL),
        renditions.full,
        "image/jpeg",
    )
    await put_object(
        rendition_key(delivery.image_path, PhotoVariant.PREVIEW),
        renditions.preview,
        "image/jpeg",
    )

    now = datetime.now(UTC)
    urls = {
        variant: build_photo_url(
            settings.PUBLIC_BASE_URL,
            settings.PHOTO_LINK_SECRET,
            incident_id,
            delivery.report_id,
            now,
            variant,
        )
        for variant in PhotoVariant
    }
    await multicast_in_chunks(
        delivery.recipients,
        build_incident_photo(urls[PhotoVariant.FULL], urls[PhotoVariant.PREVIEW]),
        key_prefix=("incident_photo", incident_id),
    )
    logger.info(
        "incident photo sent: incident_id=%s report_id=%s recipients=%s "
        "full_bytes=%s preview_bytes=%s",
        incident_id,
        delivery.report_id,
        len(delivery.recipients),
        len(renditions.full),
        len(renditions.preview),
    )
