import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api import admin_auth, admin_volunteers
from api.utils_api import app
from models import AdminUser, Volunteer, VolunteerStatus
from services.admin_auth import LoginOutcome, LoginResult
from services.volunteers import VolunteerNotFoundError

NOW = datetime(2026, 3, 2, 3, 0, tzinfo=UTC)


def admin() -> AdminUser:
    return AdminUser(id=1, username="ops", last_login_at=NOW, is_active=True)


def volunteer(status: VolunteerStatus = VolunteerStatus.PENDING) -> Volunteer:
    return Volunteer(
        id=7,
        line_user_id="UV1",
        full_name="สมศักดิ์ ใจดี",
        phone="0812345678",
        district_code="5803",
        status=status,
        approved_at=NOW if status == VolunteerStatus.APPROVED else None,
        created_at=NOW,
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

    monkeypatch.setattr(admin_auth, "SessionLocal", fake_session)
    monkeypatch.setattr(admin_volunteers, "SessionLocal", fake_session)
    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def sessions(monkeypatch):
    tokens = {}

    async def fake_resolve(session, token, now):
        return tokens.get(token)

    monkeypatch.setattr(admin_auth, "resolve_admin_session", fake_resolve)
    return tokens


@pytest.fixture
def logged_in(client, sessions):
    sessions["good-token"] = admin()
    client.cookies.set("admin_session", "good-token", path="/admin")
    return client


def use_login(monkeypatch, result: LoginResult):
    calls = []

    async def fake_login(session, username, password, now):
        calls.append((username, password))
        return result

    monkeypatch.setattr(admin_auth, "login_admin", fake_login)
    return calls


def test_login_sets_hardened_cookie(client, monkeypatch):
    use_login(
        monkeypatch,
        LoginResult(
            LoginOutcome.SUCCESS,
            admin=admin(),
            session_token="new-token",
            expires_at=NOW,
        ),
    )

    response = client.post("/admin/login", json={"username": "ops", "password": "pw"})

    assert response.status_code == 200
    assert response.json()["username"] == "ops"
    cookie = response.headers["set-cookie"]
    assert "admin_session=new-token" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/admin" in cookie


@pytest.mark.parametrize(
    "outcome", [LoginOutcome.INVALID_CREDENTIALS, LoginOutcome.LOCKED]
)
def test_login_failures_look_identical(client, monkeypatch, outcome):
    use_login(monkeypatch, LoginResult(outcome))

    response = client.post("/admin/login", json={"username": "ops", "password": "pw"})

    assert response.status_code == 401
    assert response.json()["detail"]["message"] == admin_auth.LOGIN_FAILED_MESSAGE
    assert "set-cookie" not in response.headers


def test_login_validation_error_does_not_log_password(client, caplog):
    with caplog.at_level(logging.WARNING):
        response = client.post(
            "/admin/login", json={"password": "super-secret-password"}
        )

    assert response.status_code == 422
    assert "super-secret-password" not in caplog.text


def test_me_requires_cookie(client, sessions):
    response = client.get("/admin/me")

    assert response.status_code == 401
    assert response.json()["detail"]["message"] == admin_auth.AUTH_REQUIRED_MESSAGE


def test_me_rejects_unknown_token(client, sessions):
    client.cookies.set("admin_session", "stolen-or-expired", path="/admin")

    assert client.get("/admin/me").status_code == 401


def test_me_returns_admin(logged_in):
    response = logged_in.get("/admin/me")

    assert response.status_code == 200
    assert response.json()["username"] == "ops"


def test_logout_revokes_and_clears_cookie(logged_in, monkeypatch):
    revoked = []

    async def fake_revoke(session, token, now):
        revoked.append(token)
        return True

    monkeypatch.setattr(admin_auth, "revoke_admin_session", fake_revoke)

    response = logged_in.post("/admin/logout")

    assert response.status_code == 204
    assert revoked == ["good-token"]
    assert 'admin_session=""' in response.headers["set-cookie"]


def test_volunteers_require_admin(client, sessions):
    assert client.get("/admin/volunteers").status_code == 401
    assert client.post("/admin/volunteers/7/approve").status_code == 401


@pytest.fixture
def volunteer_queries(monkeypatch):
    calls = []

    async def fake_count(session, status, district_code):
        calls.append(("count", status, district_code))
        return 120

    async def fake_list(session, status, district_code, limit, offset):
        calls.append(("list", status, district_code, limit, offset))
        return [volunteer()]

    monkeypatch.setattr(admin_volunteers, "count_volunteers", fake_count)
    monkeypatch.setattr(admin_volunteers, "list_volunteers", fake_list)
    return calls


def test_list_volunteers_paginates_with_filters(logged_in, volunteer_queries):
    response = logged_in.get(
        "/admin/volunteers",
        params={
            "status": "pending",
            "district_code": "5803",
            "limit": 20,
            "offset": 40,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["id"] == 7
    assert body["total"] == 120
    assert (body["limit"], body["offset"]) == (20, 40)
    assert volunteer_queries == [
        ("count", VolunteerStatus.PENDING, "5803"),
        ("list", VolunteerStatus.PENDING, "5803", 20, 40),
    ]


def test_list_volunteers_default_page(logged_in, volunteer_queries):
    body = logged_in.get("/admin/volunteers").json()

    assert (body["limit"], body["offset"]) == (admin_volunteers.DEFAULT_PAGE_SIZE, 0)
    assert volunteer_queries[1] == (
        "list",
        None,
        None,
        admin_volunteers.DEFAULT_PAGE_SIZE,
        0,
    )


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": admin_volunteers.MAX_PAGE_SIZE + 1},
        {"offset": -1},
        {"district_code": "58"},
    ],
)
def test_list_volunteers_rejects_bad_query(logged_in, volunteer_queries, params):
    assert logged_in.get("/admin/volunteers", params=params).status_code == 422
    assert volunteer_queries == []


def test_approve_records_admin_actor(logged_in, monkeypatch):
    calls = []

    async def fake_set(session, volunteer_id, status, now, actor):
        calls.append((volunteer_id, status, actor))
        return volunteer(status)

    monkeypatch.setattr(admin_volunteers, "set_volunteer_status", fake_set)

    response = logged_in.post("/admin/volunteers/7/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert calls == [(7, VolunteerStatus.APPROVED, "admin:ops")]


def test_unknown_action_rejected(logged_in):
    assert logged_in.post("/admin/volunteers/7/pending").status_code == 422


def test_status_change_unknown_volunteer(logged_in, monkeypatch):
    async def fake_set(session, volunteer_id, status, now, actor):
        raise VolunteerNotFoundError(volunteer_id)

    monkeypatch.setattr(admin_volunteers, "set_volunteer_status", fake_set)

    assert logged_in.post("/admin/volunteers/99/suspend").status_code == 404
