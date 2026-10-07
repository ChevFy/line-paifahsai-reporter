from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api import line_auth, volunteers
from api.utils_api import app
from line.line_id_token import InvalidIdTokenError, LineIdentity
from models import Volunteer, VolunteerStatus
from services.volunteers import RegistrationResult, UnknownDistrictError

AUTH = {"Authorization": "Bearer test-id-token"}


def valid_body() -> dict:
    return {"full_name": "สมศักดิ์ ใจดี", "phone": "0812345678", "district_code": "5803"}


def volunteer(status: VolunteerStatus = VolunteerStatus.PENDING) -> Volunteer:
    return Volunteer(
        id=7,
        line_user_id="UV1",
        full_name="สมศักดิ์ ใจดี",
        phone="0812345678",
        district_code="5803",
        status=status,
        approved_at=None,
        created_at=datetime(2026, 3, 2, 3, 0, tzinfo=UTC),
    )


class FakeSession:
    @asynccontextmanager
    async def begin(self):
        yield


@pytest.fixture
def client(monkeypatch):
    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr(volunteers, "SessionLocal", fake_session)
    return TestClient(app)


@pytest.fixture
def verified(monkeypatch):
    async def fake_verify(id_token):
        return LineIdentity(user_id="UV1", display_name="Somsak")

    monkeypatch.setattr(line_auth, "verify_id_token", fake_verify)


def use_register(monkeypatch, behavior):
    async def fake_register(session, registration):
        return behavior(registration)

    monkeypatch.setattr(volunteers, "register_volunteer", fake_register)


def test_register_returns_pending(client, verified, monkeypatch):
    registrations = []

    def register(registration):
        registrations.append(registration)
        return RegistrationResult(volunteer(), created=True)

    use_register(monkeypatch, register)
    response = client.post("/volunteers", json=valid_body(), headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["volunteer"]["status"] == "pending"
    assert "รอแอดมินอนุมัติ" in body["message"]
    assert registrations[0].line_user_id == "UV1"


def test_register_uses_token_identity_not_body(client, verified, monkeypatch):
    registrations = []

    def register(registration):
        registrations.append(registration)
        return RegistrationResult(volunteer(), created=True)

    use_register(monkeypatch, register)
    body = valid_body() | {"line_user_id": "U-someone-else"}
    client.post("/volunteers", json=body, headers=AUTH)

    assert registrations[0].line_user_id == "UV1"


def test_register_without_token_returns_401(client):
    response = client.post("/volunteers", json=valid_body())

    assert response.status_code == 401


def test_register_invalid_token_returns_401(client, monkeypatch):
    async def fake_verify(id_token):
        raise InvalidIdTokenError("bad")

    monkeypatch.setattr(line_auth, "verify_id_token", fake_verify)
    response = client.post("/volunteers", json=valid_body(), headers=AUTH)

    assert response.status_code == 401


def test_register_bad_phone_returns_422(client, verified):
    response = client.post(
        "/volunteers", json=valid_body() | {"phone": "12345"}, headers=AUTH
    )

    assert response.status_code == 422


def test_register_unknown_district_returns_422(client, verified, monkeypatch):
    def register(registration):
        raise UnknownDistrictError(registration.district_code)

    use_register(monkeypatch, register)
    response = client.post("/volunteers", json=valid_body(), headers=AUTH)

    assert response.status_code == 422


def test_me_returns_404_when_not_registered(client, verified, monkeypatch):
    async def fake_find(session, line_user_id):
        return None

    monkeypatch.setattr(volunteers, "find_volunteer_by_line_user", fake_find)
    response = client.get("/volunteers/me", headers=AUTH)

    assert response.status_code == 404


def test_me_returns_status(client, verified, monkeypatch):
    async def fake_find(session, line_user_id):
        return volunteer(VolunteerStatus.APPROVED)

    monkeypatch.setattr(volunteers, "find_volunteer_by_line_user", fake_find)
    response = client.get("/volunteers/me", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["volunteer"]["status"] == "approved"
