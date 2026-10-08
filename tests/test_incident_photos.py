from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from api import incident_photos
from api.utils_api import app
from config.config import settings
from core.storage import StorageObjectNotFoundError, StorageUnavailableError
from services.incident_photos import (
    PHOTO_LINK_TTL,
    IncidentPhoto,
    LinkStatus,
    build_photo_page_url,
    link_query,
    verify_incident_link,
)

SECRET = "s" * 40
NOW = datetime(2026, 3, 2, 3, 0, tzinfo=UTC)
JPEG = b"\xff\xd8\xffphoto"


def query_of(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def test_page_url_is_signed_and_expires_after_ttl():
    url = build_photo_page_url("https://pai.example/", SECRET, 42, NOW)
    params = query_of(url)

    assert url.startswith("https://pai.example/incidents/42/photos?")
    assert int(params["expires"]) == int((NOW + PHOTO_LINK_TTL).timestamp())
    assert (
        verify_incident_link(SECRET, 42, int(params["expires"]), params["sig"], NOW)
        == LinkStatus.VALID
    )


def test_link_for_other_incident_is_invalid():
    params = query_of(build_photo_page_url("https://pai.example", SECRET, 42, NOW))

    status = verify_incident_link(SECRET, 43, int(params["expires"]), params["sig"], NOW)

    assert status == LinkStatus.INVALID


def test_tampered_expiry_is_invalid():
    params = query_of(build_photo_page_url("https://pai.example", SECRET, 42, NOW))
    later = int(params["expires"]) + 86400

    assert verify_incident_link(SECRET, 42, later, params["sig"], NOW) == LinkStatus.INVALID


def test_expired_link():
    params = query_of(build_photo_page_url("https://pai.example", SECRET, 42, NOW))
    after = NOW + PHOTO_LINK_TTL + timedelta(seconds=1)

    status = verify_incident_link(SECRET, 42, int(params["expires"]), params["sig"], after)

    assert status == LinkStatus.EXPIRED


class FakeSession:
    pass


@pytest.fixture
def client(monkeypatch):
    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr(incident_photos, "SessionLocal", fake_session)
    return TestClient(app)


@pytest.fixture
def alerts(monkeypatch):
    recorded = []

    async def fake_alert(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(incident_photos, "record_admin_alert_safely", fake_alert)
    return recorded


def valid_query(incident_id: int = 42) -> str:
    expires = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    return link_query(settings.PHOTO_LINK_SECRET, incident_id, expires)


def use_photos(monkeypatch, photos: list[IncidentPhoto]):
    async def fake_list(session, incident_id):
        return photos

    monkeypatch.setattr(incident_photos, "list_incident_photos", fake_list)


def use_key(monkeypatch, key: str | None):
    async def fake_find(session, incident_id, report_id):
        return key

    monkeypatch.setattr(incident_photos, "find_incident_photo_key", fake_find)


def use_storage(monkeypatch, behavior):
    async def fake_get(key):
        return behavior(key)

    monkeypatch.setattr(incident_photos, "get_object", fake_get)


def test_page_lists_photos_with_signed_image_urls(client, monkeypatch):
    use_photos(monkeypatch, [IncidentPhoto(10, NOW), IncidentPhoto(11, NOW)])
    query = valid_query()

    response = client.get(f"/incidents/42/photos?{query}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["referrer-policy"] == "no-referrer"
    html = response.text
    assert "2 รูป" in html
    escaped = query.replace("&", "&amp;")
    assert f'src="photos/10?{escaped}"' in html
    assert f'src="photos/11?{escaped}"' in html
    assert 'src="/' not in html


def test_page_without_photos(client, monkeypatch):
    use_photos(monkeypatch, [])

    response = client.get(f"/incidents/42/photos?{valid_query()}")

    assert response.status_code == 200
    assert "ยังไม่มีรูป" in response.text


def test_page_rejects_bad_signature(client, monkeypatch):
    use_photos(monkeypatch, [IncidentPhoto(10, NOW)])

    response = client.get(f"/incidents/43/photos?{valid_query(42)}")

    assert response.status_code == 403
    assert "/photos/10" not in response.text


def test_page_rejects_expired_link(client):
    expires = int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())
    query = link_query(settings.PHOTO_LINK_SECRET, 42, expires)

    response = client.get(f"/incidents/42/photos?{query}")

    assert response.status_code == 410


def test_image_served_from_storage(client, monkeypatch):
    use_key(monkeypatch, "reports/10/a.jpg")
    use_storage(monkeypatch, lambda key: (JPEG, "image/jpeg"))

    response = client.get(f"/incidents/42/photos/10?{valid_query()}")

    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_image_rejects_bad_signature(client, monkeypatch):
    use_key(monkeypatch, "reports/10/a.jpg")
    use_storage(monkeypatch, lambda key: (JPEG, "image/jpeg"))

    response = client.get(f"/incidents/42/photos/10?{valid_query(99)}")

    assert response.status_code == 403
    assert response.content != JPEG


def test_image_of_other_incident_returns_404(client, monkeypatch):
    use_key(monkeypatch, None)

    response = client.get(f"/incidents/42/photos/10?{valid_query()}")

    assert response.status_code == 404


def test_storage_down_logs_and_alerts(client, alerts, monkeypatch, caplog):
    use_key(monkeypatch, "reports/10/a.jpg")

    def fail(key):
        raise StorageUnavailableError("EndpointConnectionError: refused")

    use_storage(monkeypatch, fail)

    response = client.get(f"/incidents/42/photos/10?{valid_query()}")

    assert response.status_code == 503
    assert alerts[0]["alert_type"] == "report_image_storage_unavailable"
    assert alerts[0]["payload"]["report_id"] == 10
    assert "image storage unavailable on read" in caplog.text


def test_missing_object_alerts(client, alerts, monkeypatch):
    use_key(monkeypatch, "reports/10/a.jpg")

    def missing(key):
        raise StorageObjectNotFoundError(key)

    use_storage(monkeypatch, missing)

    response = client.get(f"/incidents/42/photos/10?{valid_query()}")

    assert response.status_code == 404
    assert alerts[0]["alert_type"] == incident_photos.ALERT_IMAGE_MISSING
