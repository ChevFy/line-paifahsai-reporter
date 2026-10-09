from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api import incidents
from api.utils_api import app
from models import IncidentStatus
from services.incidents import ActiveIncident, ActiveIncidentList


@pytest.fixture
def client():
    return TestClient(app)


def use_list(monkeypatch, result: ActiveIncidentList, calls: list | None = None):
    async def fake_list(session, district_code, limit):
        if calls is not None:
            calls.append({"district_code": district_code, "limit": limit})
        return result

    monkeypatch.setattr(incidents, "list_active_incidents", fake_list)


def active_incident(incident_id: int = 1) -> ActiveIncident:
    return ActiveIncident(
        id=incident_id,
        latitude=19.36,
        longitude=98.44,
        district_code="5803",
        status=IncidentStatus.OPEN,
        report_count=2,
        created_at=datetime(2026, 3, 2, 3, 0, tzinfo=UTC),
    )


def test_returns_active_incidents_with_emergency_phone(client, monkeypatch):
    calls = []
    use_list(monkeypatch, ActiveIncidentList([active_incident()], False), calls)

    response = client.get("/incidents/active", params={"district_code": "5803"})

    assert response.status_code == 200
    body = response.json()
    assert body["emergency_phone"] == "1362"
    assert body["truncated"] is False
    assert body["incidents"][0] == {
        "id": 1,
        "latitude": 19.36,
        "longitude": 98.44,
        "district_code": "5803",
        "status": "open",
        "report_count": 2,
        "created_at": "2026-03-02T03:00:00Z",
    }
    assert calls == [
        {"district_code": "5803", "limit": incidents.MAX_ACTIVE_INCIDENTS}
    ]


def test_does_not_expose_description_or_reporter(client, monkeypatch):
    use_list(monkeypatch, ActiveIncidentList([active_incident()], False))

    incident = client.get("/incidents/active").json()["incidents"][0]

    assert "description" not in incident
    assert "reporter_user_id" not in incident


def test_reports_truncation(client, monkeypatch):
    use_list(monkeypatch, ActiveIncidentList([active_incident()], True))

    response = client.get("/incidents/active")

    assert response.json()["truncated"] is True


def test_invalid_district_code_returns_422(client):
    response = client.get("/incidents/active", params={"district_code": "abc"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"]
    assert detail["errors"][0]["loc"] == ["query", "district_code"]
