import io
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
import sqlalchemy as sa
from conftest import PAI, requires_postgis
from geoalchemy2 import WKTElement
from PIL import Image
from test_volunteer_flow import NOW, accept, add_incident, add_volunteer

from core.storage import StorageObjectNotFoundError, StorageUnavailableError
from jobs import common as jobs_common
from jobs import dispatch as dispatch_job
from jobs import photo_delivery as photo_job
from models import IncidentStatus, Job, LineUser, Report
from services.incident_photos import verify_incident_link
from services.jobs import PermanentJobError
from services.ops_date import ops_date_for
from services.photo_delivery import JOB_SEND_INCIDENT_PHOTO
from services.photo_renditions import (
    LINE_PREVIEW_MAX_BYTES,
    PREVIEW_MAX_SIDE,
    PhotoVariant,
    UnreadableImageError,
    render_line_images,
    rendition_key,
)
from services.report_images import ImageType, ReportImage, save_report_image

GPS_TAG = 0x8825


def encode(image: Image.Image, fmt: str, **kwargs) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def jpeg_with_gps(size=(3000, 2000)) -> bytes:
    exif = Image.Exif()
    exif[GPS_TAG] = {1: "N", 2: (19.0, 21.0, 36.0)}
    return encode(Image.new("RGB", size, "orange"), "JPEG", exif=exif)


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_renders_jpeg_without_exif_and_within_line_limits():
    renditions = render_line_images(jpeg_with_gps())

    full = opened(renditions.full)
    preview = opened(renditions.preview)
    assert full.format == "JPEG" and preview.format == "JPEG"
    assert max(full.size) == 2048
    assert max(preview.size) == PREVIEW_MAX_SIDE
    assert len(renditions.preview) <= LINE_PREVIEW_MAX_BYTES
    assert GPS_TAG not in full.getexif()
    assert len(full.getexif()) == 0


def test_converts_heic_and_transparent_png():
    from pillow_heif import register_heif_opener

    register_heif_opener()
    heic = encode(Image.new("RGB", (800, 600), "red"), "HEIF")
    png = encode(Image.new("RGBA", (300, 300), (0, 0, 0, 0)), "PNG")

    for data in (heic, png):
        assert opened(render_line_images(data).full).format == "JPEG"


def test_small_image_is_not_upscaled():
    renditions = render_line_images(encode(Image.new("RGB", (200, 100)), "PNG"))

    assert opened(renditions.full).size == (200, 100)


@pytest.mark.parametrize("data", [b"", b"\xff\xd8\xffnot really a jpeg", b"%PDF-1.7"])
def test_unreadable_image_raises(data):
    with pytest.raises(UnreadableImageError):
        render_line_images(data)


def test_rendition_key_is_derived_from_original():
    key = rendition_key("reports/7/abc.heic", PhotoVariant.PREVIEW)

    assert key == "reports/7/abc.heic.preview.jpg"


class FakeLine:
    def __init__(self):
        self.calls = []

    async def multicast(self, to, messages, retry_key=None):
        self.calls.append({"to": list(to), "message": messages, "retry_key": retry_key})


class FakeObjectStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.read_error: Exception | None = None

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    async def get(self, key: str) -> tuple[bytes, str]:
        if self.read_error is not None:
            raise self.read_error
        if key not in self.objects:
            raise StorageObjectNotFoundError(key)
        return self.objects[key], "image/jpeg"


@pytest.fixture
def fake_line(monkeypatch):
    line = FakeLine()
    monkeypatch.setattr(jobs_common, "get_line_service", lambda: line)
    return line


@pytest.fixture
def store(monkeypatch):
    objects = FakeObjectStore()
    monkeypatch.setattr(photo_job, "get_object", objects.get)
    monkeypatch.setattr(photo_job, "put_object", objects.put)
    return objects


async def add_report(sessionmaker, incident_id: int, user_id: str = "UR1") -> int:
    async with sessionmaker() as session, session.begin():
        await session.merge(LineUser(user_id=user_id))
        report = Report(
            incident_id=incident_id,
            reporter_user_id=user_id,
            location=WKTElement("SRID=4326;POINT(98.44 19.36)", extended=True),
            ops_date=ops_date_for(NOW),
            client_request_id=uuid.uuid4(),
        )
        session.add(report)
        await session.flush()
        return report.id


async def upload(sessionmaker, store: FakeObjectStore, report_id: int, user_id="UR1"):
    return await save_report_image(
        sessionmaker,
        store.put,
        ReportImage(report_id, user_id, jpeg_with_gps((640, 480)), ImageType("jpg", "image/jpeg")),
    )


async def photo_jobs(sessionmaker) -> list[Job]:
    async with sessionmaker() as session:
        rows = await session.execute(
            sa.select(Job).where(Job.job_type == JOB_SEND_INCIDENT_PHOTO)
        )
        return list(rows.scalars())


async def dispatch(sessionmaker, incident_id: int) -> None:
    await dispatch_job.handle_dispatch_incident(
        {"incident_id": incident_id, "reason": "initial", "round": "initial"},
        sessionmaker,
    )


@pytest.mark.anyio
@requires_postgis
async def test_photo_uploaded_before_dispatch_is_sent_by_dispatch(
    sessionmaker, fake_line, store
):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    report_id = await add_report(sessionmaker, incident_id)

    await upload(sessionmaker, store, report_id)
    assert await photo_jobs(sessionmaker) == []

    await dispatch(sessionmaker, incident_id)

    jobs = await photo_jobs(sessionmaker)
    assert [job.payload for job in jobs] == [{"incident_id": incident_id}]


@pytest.mark.anyio
@requires_postgis
async def test_photo_uploaded_after_dispatch_is_queued_by_upload(
    sessionmaker, fake_line, store
):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    report_id = await add_report(sessionmaker, incident_id)
    await dispatch(sessionmaker, incident_id)
    assert await photo_jobs(sessionmaker) == []

    await upload(sessionmaker, store, report_id)

    assert len(await photo_jobs(sessionmaker)) == 1


@pytest.mark.anyio
@requires_postgis
async def test_only_first_photo_of_incident_is_queued(sessionmaker, fake_line, store):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    first = await add_report(sessionmaker, incident_id, "UR1")
    second = await add_report(sessionmaker, incident_id, "UR2")
    await dispatch(sessionmaker, incident_id)

    await upload(sessionmaker, store, first, "UR1")
    await upload(sessionmaker, store, second, "UR2")
    await dispatch_job.handle_dispatch_incident(
        {"incident_id": incident_id, "reason": "escalation", "round": "escalation"},
        sessionmaker,
    )

    assert len(await photo_jobs(sessionmaker)) == 1


@pytest.mark.anyio
@requires_postgis
async def test_photo_for_closed_incident_is_not_queued(sessionmaker, store):
    incident_id = await add_incident(sessionmaker, IncidentStatus.CLOSED)
    report_id = await add_report(sessionmaker, incident_id)

    await upload(sessionmaker, store, report_id)

    assert await photo_jobs(sessionmaker) == []


@pytest.mark.anyio
@requires_postgis
async def test_no_volunteers_means_no_photo_job(sessionmaker, fake_line, store):
    incident_id = await add_incident(sessionmaker)
    report_id = await add_report(sessionmaker, incident_id)
    await upload(sessionmaker, store, report_id)

    await dispatch(sessionmaker, incident_id)

    assert await photo_jobs(sessionmaker) == []
    assert fake_line.calls == []


@pytest.mark.anyio
@requires_postgis
async def test_photo_job_multicasts_signed_jpeg_urls(sessionmaker, fake_line, store):
    await add_volunteer(sessionmaker, "UV1")
    await add_volunteer(sessionmaker, "UV2")
    incident_id = await add_incident(sessionmaker)
    report_id = await add_report(sessionmaker, incident_id)
    await accept(sessionmaker, "UV1", incident_id)
    await upload(sessionmaker, store, report_id)
    original_key = next(iter(store.objects))

    await photo_job.handle_send_incident_photo({"incident_id": incident_id}, sessionmaker)

    assert len(fake_line.calls) == 1
    call = fake_line.calls[0]
    assert call["to"] == ["UV1", "UV2"]
    message = call["message"]
    for url, variant in (
        (message.original_content_url, PhotoVariant.FULL),
        (message.preview_image_url, PhotoVariant.PREVIEW),
    ):
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.path.endswith(f"/incidents/{incident_id}/photos/{report_id}")
        query = parse_qs(parsed.query)
        assert query["variant"] == [variant.value]
        assert verify_incident_link(
            "test-photo-link-secret-0123456789abcdef",
            incident_id,
            int(query["expires"][0]),
            query["sig"][0],
            NOW,
        ).value == "valid"
        assert opened(store.objects[rendition_key(original_key, variant)]).format == "JPEG"


@pytest.mark.anyio
@requires_postgis
async def test_photo_job_skips_closed_incident(sessionmaker, fake_line, store):
    incident_id = await add_incident(sessionmaker, IncidentStatus.CLOSED)
    report_id = await add_report(sessionmaker, incident_id)
    async with sessionmaker() as session, session.begin():
        await session.execute(
            sa.update(Report).where(Report.id == report_id).values(image_path="k")
        )

    await photo_job.handle_send_incident_photo({"incident_id": incident_id}, sessionmaker)

    assert fake_line.calls == []


@pytest.mark.anyio
@requires_postgis
async def test_photo_job_unreadable_image_is_permanent(sessionmaker, fake_line, store):
    await add_volunteer(sessionmaker, "UV1", district_code=PAI)
    incident_id = await add_incident(sessionmaker)
    report_id = await add_report(sessionmaker, incident_id)
    await save_report_image(
        sessionmaker,
        store.put,
        ReportImage(report_id, "UR1", b"\xff\xd8\xffbroken", ImageType("jpg", "image/jpeg")),
    )

    with pytest.raises(PermanentJobError):
        await photo_job.handle_send_incident_photo(
            {"incident_id": incident_id}, sessionmaker
        )
    assert fake_line.calls == []


@pytest.mark.anyio
@requires_postgis
async def test_photo_job_storage_down_is_retried(sessionmaker, fake_line, store):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    report_id = await add_report(sessionmaker, incident_id)
    await upload(sessionmaker, store, report_id)
    store.read_error = StorageUnavailableError("connection refused")

    with pytest.raises(StorageUnavailableError):
        await photo_job.handle_send_incident_photo(
            {"incident_id": incident_id}, sessionmaker
        )
    assert fake_line.calls == []
