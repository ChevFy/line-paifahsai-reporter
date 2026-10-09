from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from conftest import requires_postgis

from models import AdminAlert, AdminUser
from services import admin_auth
from services.admin_auth import (
    ALERT_ADMIN_LOGIN_LOCKED,
    LOCKOUT_DURATION,
    MAX_FAILED_LOGINS,
    SESSION_TTL,
    AdminUserExistsError,
    InvalidPasswordError,
    LoginOutcome,
    check_password,
    create_admin,
    hash_password,
    login_admin,
    resolve_admin_session,
    revoke_admin_session,
    set_admin_active,
    set_admin_password,
)

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 3, 2, 3, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    monkeypatch.setattr(admin_auth, "BCRYPT_ROUNDS", 4)


async def test_hash_and_check_password():
    hashed = await hash_password(PASSWORD)

    assert hashed != PASSWORD
    assert await check_password(PASSWORD, hashed)
    assert not await check_password("wrong-password-123", hashed)
    assert not await check_password(PASSWORD, None)


@pytest.mark.parametrize("password", ["short", "ก" * 25])
async def test_hash_password_rejects_out_of_range(password):
    with pytest.raises(InvalidPasswordError):
        await hash_password(password)


async def test_check_password_rejects_over_bcrypt_limit():
    hashed = await hash_password("a" * 72)

    assert not await check_password("a" * 72 + "extra", hashed)


async def add_admin(sessionmaker, username: str = "Ops") -> int:
    async with sessionmaker() as session, session.begin():
        return (await create_admin(session, username, PASSWORD)).id


async def login(sessionmaker, password: str = PASSWORD, now: datetime = NOW):
    async with sessionmaker() as session, session.begin():
        return await login_admin(session, " OPS ", password, now)


async def resolve(sessionmaker, token: str, now: datetime = NOW):
    async with sessionmaker() as session:
        return await resolve_admin_session(session, token, now)


@requires_postgis
async def test_login_creates_session(sessionmaker):
    admin_id = await add_admin(sessionmaker)

    result = await login(sessionmaker)

    assert result.outcome == LoginOutcome.SUCCESS
    assert result.expires_at == NOW + SESSION_TTL
    found = await resolve(sessionmaker, result.session_token)
    assert found.id == admin_id
    assert await resolve(sessionmaker, result.session_token, NOW + SESSION_TTL) is None


@requires_postgis
async def test_session_token_is_not_stored_raw(sessionmaker):
    await add_admin(sessionmaker)
    result = await login(sessionmaker)

    async with sessionmaker() as session:
        stored = (
            await session.execute(sa.text("SELECT token_hash FROM admin_sessions"))
        ).scalar_one()
    assert stored != result.session_token


@requires_postgis
async def test_duplicate_username_rejected(sessionmaker):
    await add_admin(sessionmaker, "ops")

    with pytest.raises(AdminUserExistsError):
        await add_admin(sessionmaker, " OPS ")


@requires_postgis
async def test_unknown_user_is_invalid(sessionmaker):
    result = await login(sessionmaker)

    assert result.outcome == LoginOutcome.INVALID_CREDENTIALS


@requires_postgis
async def test_failed_count_persists_and_locks(sessionmaker):
    admin_id = await add_admin(sessionmaker)

    for _ in range(MAX_FAILED_LOGINS - 1):
        assert (
            await login(sessionmaker, "wrong-password-123")
        ).outcome == LoginOutcome.INVALID_CREDENTIALS

    async with sessionmaker() as session:
        admin = await session.get(AdminUser, admin_id)
        assert admin.failed_login_count == MAX_FAILED_LOGINS - 1

    await login(sessionmaker, "wrong-password-123")

    locked = await login(sessionmaker)
    assert locked.outcome == LoginOutcome.LOCKED
    assert locked.session_token is None

    async with sessionmaker() as session:
        alert = (await session.execute(sa.select(AdminAlert))).scalar_one()
    assert alert.alert_type == ALERT_ADMIN_LOGIN_LOCKED
    assert alert.dedup_key == f"{ALERT_ADMIN_LOGIN_LOCKED}:{admin_id}"

    after = await login(sessionmaker, now=NOW + LOCKOUT_DURATION + timedelta(seconds=1))
    assert after.outcome == LoginOutcome.SUCCESS


@requires_postgis
async def test_logout_revokes_only_that_session(sessionmaker):
    await add_admin(sessionmaker)
    first = await login(sessionmaker)
    second = await login(sessionmaker)

    async with sessionmaker() as session, session.begin():
        assert await revoke_admin_session(session, first.session_token, NOW)
        assert not await revoke_admin_session(session, first.session_token, NOW)

    assert await resolve(sessionmaker, first.session_token) is None
    assert await resolve(sessionmaker, second.session_token) is not None


@requires_postgis
async def test_disable_revokes_sessions_and_blocks_login(sessionmaker):
    await add_admin(sessionmaker)
    result = await login(sessionmaker)

    async with sessionmaker() as session, session.begin():
        await set_admin_active(session, "ops", False, NOW)

    assert await resolve(sessionmaker, result.session_token) is None
    assert (await login(sessionmaker)).outcome == LoginOutcome.INVALID_CREDENTIALS


@requires_postgis
async def test_password_change_revokes_sessions(sessionmaker):
    await add_admin(sessionmaker)
    result = await login(sessionmaker)

    async with sessionmaker() as session, session.begin():
        await set_admin_password(session, "ops", "another-long-password", NOW)

    assert await resolve(sessionmaker, result.session_token) is None
    assert (await login(sessionmaker)).outcome == LoginOutcome.INVALID_CREDENTIALS
    assert (
        await login(sessionmaker, "another-long-password")
    ).outcome == LoginOutcome.SUCCESS
