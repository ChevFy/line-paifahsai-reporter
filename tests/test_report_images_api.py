import pytest
from fastapi.testclient import TestClient

from api import line_auth, report_images
from api.utils_api import app
from core.storage import StorageUnavailableError
from line.line_id_token import LineIdentity
from services.report_images import ImageOutcome

AUTH = {"Authorization": "Bearer test-id-token"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def verified(monkeypatch):
    async def fake_verify(id_token):
        return LineIdentity(user_id="U123", display_name="Somchai")

    monkeypatch.setattr(line_auth, "verify_id_token", fake_verify)


@pytest.fixture
def alerts(monkeypatch):
    recorded = []

    async def fake_alert(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(report_images, "record_admin_alert_safely", fake_alert)
    return recorded


def use_save(monkeypatch, behavior):
    calls = []

    async def fake_save(sessionmaker, store, image):
        calls.append(image)
        return behavior()

    monkeypatch.setattr(report_images, "save_report_image", fake_save)
    return calls


def upload(client, data: bytes = JPEG, headers: dict | None = AUTH):
    return client.post(
        "/reports/10/image",
        files={"image": ("fire.jpg", data, "image/jpeg")},
        headers=headers,
    )


def assert_has_emergency_phone(body: dict):
    assert body["emergency_phone"] == "1362"
    assert "1362" in body["message"]


def test_stores_image(client, verified, monkeypatch):
    calls = use_save(monkeypatch, lambda: ImageOutcome.STORED)

    response = upload(client)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "stored"
    assert_has_emergency_phone(body)
    assert calls[0].report_id == 10
    assert calls[0].reporter_user_id == "U123"
    assert calls[0].image_type.content_type == "image/jpeg"


def test_already_attached_returns_200(client, verified, monkeypatch):
    use_save(monkeypatch, lambda: ImageOutcome.ALREADY_ATTACHED)

    response = upload(client)

    assert response.status_code == 200
    assert response.json()["outcome"] == "already_attached"


def test_foreign_report_returns_404(client, verified, monkeypatch):
    use_save(monkeypatch, lambda: ImageOutcome.REPORT_NOT_FOUND)

    response = upload(client)

    assert response.status_code == 404
    assert_has_emergency_phone(response.json()["detail"])


def test_storage_down_logs_alerts_and_keeps_report(
    client, verified, alerts, monkeypatch, caplog
):
    def fail():
        raise StorageUnavailableError("EndpointConnectionError: connection refused")

    use_save(monkeypatch, fail)

    response = upload(client)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert_has_emergency_phone(detail)
    assert "ไม่ต้องแจ้งซ้ำ" in detail["message"]
    assert alerts[0]["alert_type"] == report_images.ALERT_IMAGE_STORAGE_UNAVAILABLE
    assert alerts[0]["dedup_key"] == report_images.ALERT_IMAGE_STORAGE_UNAVAILABLE
    assert alerts[0]["payload"]["report_id"] == 10
    assert "connection refused" in alerts[0]["payload"]["error"]
    assert "image storage unavailable" in caplog.text


def test_unexpected_error_alerts(client, verified, alerts, monkeypatch):
    def fail():
        raise RuntimeError("db down")

    use_save(monkeypatch, fail)

    response = upload(client)

    assert response.status_code == 500
    assert_has_emergency_phone(response.json()["detail"])
    assert alerts[0]["alert_type"] == report_images.ALERT_IMAGE_FAILED


def test_rejects_non_image(client, verified, monkeypatch):
    calls = use_save(monkeypatch, lambda: ImageOutcome.STORED)

    response = upload(client, data=b"%PDF-1.7 not an image")

    assert response.status_code == 415
    assert_has_emergency_phone(response.json()["detail"])
    assert calls == []


def test_rejects_oversized_image(client, verified, monkeypatch):
    calls = use_save(monkeypatch, lambda: ImageOutcome.STORED)
    monkeypatch.setattr(report_images, "MAX_IMAGE_BYTES", 32)

    response = upload(client)

    assert response.status_code == 413
    assert calls == []


def test_requires_token(client):
    response = upload(client, headers=None)

    assert response.status_code == 401
    assert_has_emergency_phone(response.json()["detail"])
