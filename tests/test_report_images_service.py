import uuid
from datetime import date

import pytest
from geoalchemy2 import WKTElement

from conftest import requires_postgis
from core.storage import StorageUnavailableError
from models import LineUser, Report
from services.report_images import (
    ImageOutcome,
    ImageType,
    ReportImage,
    detect_image_type,
    save_report_image,
)

JPEG_TYPE = ImageType("jpg", "image/jpeg")


@pytest.mark.parametrize(
    ("data", "extension"),
    [
        (b"\xff\xd8\xff\xe0rest", "jpg"),
        (b"\x89PNG\r\n\x1a\nrest", "png"),
        (b"RIFF\x00\x00\x00\x00WEBPrest", "webp"),
        (b"\x00\x00\x00\x18ftypheicrest", "heic"),
    ],
)
def test_detects_image_type(data, extension):
    assert detect_image_type(data).extension == extension


@pytest.mark.parametrize("data", [b"", b"%PDF-1.7", b"<svg></svg>", b"GIF89a"])
def test_rejects_unknown_type(data):
    assert detect_image_type(data) is None


class FakeStorage:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.objects: dict[str, bytes] = {}

    async def __call__(self, key: str, data: bytes, content_type: str) -> None:
        if self.error is not None:
            raise self.error
        self.objects[key] = data


async def add_report(sessionmaker, user_id: str = "U1") -> int:
    async with sessionmaker() as session, session.begin():
        session.add(LineUser(user_id=user_id, display_name="Somchai"))
        report = Report(
            reporter_user_id=user_id,
            location=WKTElement("POINT(98.44 19.36)", srid=4326),
            ops_date=date(2026, 3, 2),
            client_request_id=uuid.uuid4(),
        )
        session.add(report)
        await session.flush()
        return report.id


async def image_path(sessionmaker, report_id: int) -> str | None:
    async with sessionmaker() as session:
        return (await session.get(Report, report_id)).image_path


def image(report_id: int, user_id: str = "U1") -> ReportImage:
    return ReportImage(report_id, user_id, b"\xff\xd8\xffdata", JPEG_TYPE)


@pytest.mark.anyio
@requires_postgis
async def test_stores_and_attaches(sessionmaker):
    report_id = await add_report(sessionmaker)
    storage = FakeStorage()

    outcome = await save_report_image(sessionmaker, storage, image(report_id))

    assert outcome == ImageOutcome.STORED
    path = await image_path(sessionmaker, report_id)
    assert path.startswith(f"reports/{report_id}/") and path.endswith(".jpg")
    assert storage.objects[path] == b"\xff\xd8\xffdata"


@pytest.mark.anyio
@requires_postgis
async def test_second_upload_keeps_first(sessionmaker):
    report_id = await add_report(sessionmaker)
    storage = FakeStorage()
    await save_report_image(sessionmaker, storage, image(report_id))
    first = await image_path(sessionmaker, report_id)

    outcome = await save_report_image(sessionmaker, storage, image(report_id))

    assert outcome == ImageOutcome.ALREADY_ATTACHED
    assert await image_path(sessionmaker, report_id) == first
    assert len(storage.objects) == 1


@pytest.mark.anyio
@requires_postgis
async def test_other_users_report_not_found(sessionmaker):
    report_id = await add_report(sessionmaker, user_id="U1")
    storage = FakeStorage()

    outcome = await save_report_image(sessionmaker, storage, image(report_id, "U2"))

    assert outcome == ImageOutcome.REPORT_NOT_FOUND
    assert storage.objects == {}


@pytest.mark.anyio
@requires_postgis
async def test_storage_down_leaves_report_intact(sessionmaker):
    report_id = await add_report(sessionmaker)
    storage = FakeStorage(StorageUnavailableError("down"))

    with pytest.raises(StorageUnavailableError):
        await save_report_image(sessionmaker, storage, image(report_id))

    async with sessionmaker() as session:
        report = await session.get(Report, report_id)
    assert report is not None
    assert report.image_path is None
