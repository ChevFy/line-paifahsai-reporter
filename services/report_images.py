import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from models import Report

logger = logging.getLogger(__name__)

StoreObject = Callable[[str, bytes, str], Awaitable[None]]


class ImageOutcome(StrEnum):
    STORED = "stored"
    ALREADY_ATTACHED = "already_attached"
    REPORT_NOT_FOUND = "report_not_found"


@dataclass(frozen=True)
class ImageType:
    extension: str
    content_type: str


@dataclass(frozen=True)
class ReportImage:
    report_id: int
    reporter_user_id: str
    data: bytes
    image_type: ImageType


HEIF_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"mif1"}


def detect_image_type(data: bytes) -> ImageType | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ImageType("jpg", "image/jpeg")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ImageType("png", "image/png")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ImageType("webp", "image/webp")
    if data[4:8] == b"ftyp" and data[8:12] in HEIF_BRANDS:
        return ImageType("heic", "image/heic")
    return None


def build_image_key(report_id: int, image_type: ImageType) -> str:
    return f"reports/{report_id}/{uuid.uuid4()}.{image_type.extension}"


async def save_report_image(
    sessionmaker: async_sessionmaker,
    store: StoreObject,
    image: ReportImage,
) -> ImageOutcome:
    async with sessionmaker() as session:
        report = await session.get(Report, image.report_id)
    if report is None or report.reporter_user_id != image.reporter_user_id:
        logger.warning(
            "image for unknown or foreign report: report_id=%s user_id=%s",
            image.report_id,
            image.reporter_user_id,
        )
        return ImageOutcome.REPORT_NOT_FOUND
    if report.image_path is not None:
        logger.info("report image already attached: report_id=%s", image.report_id)
        return ImageOutcome.ALREADY_ATTACHED

    key = build_image_key(image.report_id, image.image_type)
    await store(key, image.data, image.image_type.content_type)

    async with sessionmaker() as session, session.begin():
        attached = (
            await session.execute(
                sa.update(Report)
                .where(Report.id == image.report_id, Report.image_path.is_(None))
                .values(image_path=key)
                .returning(Report.id)
            )
        ).scalar_one_or_none()
    if attached is None:
        logger.warning(
            "report image attached concurrently, stored object unused: "
            "report_id=%s key=%s",
            image.report_id,
            key,
        )
        return ImageOutcome.ALREADY_ATTACHED

    logger.info(
        "report image attached: report_id=%s key=%s bytes=%s",
        image.report_id,
        key,
        len(image.data),
    )
    return ImageOutcome.STORED
