import uuid

import pytest
from fastapi.testclient import TestClient

from api import reports
from api.utils_api import app
from line.line_id_token import InvalidIdTokenError, LineIdentity
from services.reports import ReportOutcome, ReportResult, UnknownDistrictError

AUTH = {"Authorization": "Bearer test-id-token"}


def valid_body() -> dict:
    return {
        "client_request_id": str(uuid.uuid4()),
        "latitude": 19.36,
        "longitude": 98.44,
        "district_code": "5803",
        "description": "เห็นควันบนดอย",
    }


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def alerts(monkeypatch):
    recorded = []

    async def fake_alert(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(reports, "record_admin_alert_safely", fake_alert)
    return recorded


@pytest.fixture
def verified(monkeypatch):
    async def fake_verify(id_token):
        return LineIdentity(user_id="U123", display_name="Somchai")

    monkeypatch.setattr(reports, "verify_id_token", fake_verify)


def use_submit(monkeypatch, behavior):
    async def fake_submit(session, submission, now):
        return behavior(submission)

    monkeypatch.setattr(reports, "submit_report", fake_submit)


def assert_has_emergency_phone(detail: dict):
    assert detail["emergency_phone"] == "1362"
    assert "1362" in detail["message"]


def test_success_response_includes_emergency_phone(client, verified, monkeypatch):
    use_submit(
        monkeypatch,
        lambda submission: ReportResult(10, 20, ReportOutcome.NEW_INCIDENT),
    )
    response = client.post("/reports", json=valid_body(), headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == 20
    assert body["outcome"] == "new_incident"
    assert_has_emergency_phone(body)


def test_missing_token_returns_401_with_emergency_phone(client):
    response = client.post("/reports", json=valid_body())

    assert response.status_code == 401
    assert_has_emergency_phone(response.json()["detail"])


def test_invalid_token_returns_401(client, monkeypatch):
    async def fake_verify(id_token):
        raise InvalidIdTokenError("bad")

    monkeypatch.setattr(reports, "verify_id_token", fake_verify)
    response = client.post("/reports", json=valid_body(), headers=AUTH)

    assert response.status_code == 401
    assert_has_emergency_phone(response.json()["detail"])


def test_location_outside_thailand_returns_422_with_emergency_phone(client):
    body = valid_body() | {"latitude": 35.0}
    response = client.post("/reports", json=body, headers=AUTH)

    assert response.status_code == 422
    assert_has_emergency_phone(response.json()["detail"])


def test_unknown_district_returns_422(client, verified, monkeypatch):
    def raise_unknown(submission):
        raise UnknownDistrictError(submission.district_code)

    use_submit(monkeypatch, raise_unknown)
    response = client.post("/reports", json=valid_body(), headers=AUTH)

    assert response.status_code == 422
    assert_has_emergency_phone(response.json()["detail"])


def test_unexpected_error_returns_500_and_alerts_admin(
    client, verified, alerts, monkeypatch
):
    def explode(submission):
        raise RuntimeError("db down")

    use_submit(monkeypatch, explode)
    response = client.post("/reports", json=valid_body(), headers=AUTH)

    assert response.status_code == 500
    assert_has_emergency_phone(response.json()["detail"])
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == reports.ALERT_REPORT_FAILED
