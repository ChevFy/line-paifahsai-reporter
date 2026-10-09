import asyncio
import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from functools import cache

import bcrypt
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import AdminSession, AdminUser, AlertSeverity
from services.admin_alerts import record_admin_alert

logger = logging.getLogger(__name__)

ALERT_ADMIN_LOGIN_LOCKED = "admin_login_locked"

SESSION_TTL = timedelta(hours=12)
MAX_FAILED_LOGINS = 10
LOCKOUT_DURATION = timedelta(minutes=15)
MIN_PASSWORD_LENGTH = 12
BCRYPT_MAX_BYTES = 72
BCRYPT_ROUNDS = 12


class LoginOutcome(StrEnum):
    SUCCESS = "success"
    INVALID_CREDENTIALS = "invalid_credentials"
    LOCKED = "locked"


@dataclass(frozen=True)
class LoginResult:
    outcome: LoginOutcome
    admin: AdminUser | None = None
    session_token: str | None = None
    expires_at: datetime | None = None


class InvalidPasswordError(ValueError):
    pass


class AdminUserExistsError(Exception):
    pass


class AdminUserNotFoundError(Exception):
    pass


def normalize_username(username: str) -> str:
    return username.strip().lower()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    if len(password.encode()) > BCRYPT_MAX_BYTES:
        raise InvalidPasswordError(
            f"password must be at most {BCRYPT_MAX_BYTES} bytes (bcrypt limit)"
        )


async def hash_password(password: str) -> str:
    validate_password(password)
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = await asyncio.to_thread(bcrypt.hashpw, password.encode(), salt)
    return hashed.decode()


@cache
def dummy_password_hash() -> bytes:
    return bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


async def check_password(password: str, password_hash: str | None) -> bool:
    encoded = password.encode()
    usable = password_hash is not None and len(encoded) <= BCRYPT_MAX_BYTES
    target = password_hash.encode() if usable else dummy_password_hash()
    matched = await asyncio.to_thread(
        bcrypt.checkpw, encoded[:BCRYPT_MAX_BYTES], target
    )
    return usable and matched


async def find_admin_by_username(
    session: AsyncSession,
    username: str,
    for_update: bool = False,
) -> AdminUser | None:
    statement = sa.select(AdminUser).where(
        AdminUser.username == normalize_username(username)
    )
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def login_admin(
    session: AsyncSession,
    username: str,
    password: str,
    now: datetime,
) -> LoginResult:
    admin = await find_admin_by_username(session, username, for_update=True)

    if admin is None or not admin.is_active:
        await check_password(password, None)
        logger.warning(
            "admin login failed: username=%s reason=%s",
            normalize_username(username),
            "unknown_user" if admin is None else "inactive",
        )
        return LoginResult(LoginOutcome.INVALID_CREDENTIALS)

    if admin.locked_until is not None and admin.locked_until > now:
        await check_password(password, None)
        logger.warning(
            "admin login rejected while locked: admin_id=%s locked_until=%s",
            admin.id,
            admin.locked_until,
        )
        return LoginResult(LoginOutcome.LOCKED)

    if not await check_password(password, admin.password_hash):
        await record_failed_login(session, admin, now)
        return LoginResult(LoginOutcome.INVALID_CREDENTIALS)

    admin.failed_login_count = 0
    admin.locked_until = None
    admin.last_login_at = now
    token = secrets.token_urlsafe(32)
    expires_at = now + SESSION_TTL
    session.add(
        AdminSession(
            token_hash=hash_session_token(token),
            admin_user_id=admin.id,
            created_at=now,
            expires_at=expires_at,
        )
    )
    await session.flush()

    logger.info("admin logged in: admin_id=%s username=%s", admin.id, admin.username)
    return LoginResult(
        LoginOutcome.SUCCESS,
        admin=admin,
        session_token=token,
        expires_at=expires_at,
    )


async def record_failed_login(
    session: AsyncSession,
    admin: AdminUser,
    now: datetime,
) -> None:
    admin.failed_login_count += 1
    logger.warning(
        "admin login failed: admin_id=%s reason=wrong_password failed_count=%s",
        admin.id,
        admin.failed_login_count,
    )
    if admin.failed_login_count >= MAX_FAILED_LOGINS:
        admin.locked_until = now + LOCKOUT_DURATION
        admin.failed_login_count = 0
        logger.error(
            "admin account locked: admin_id=%s locked_until=%s",
            admin.id,
            admin.locked_until,
        )
        await record_admin_alert(
            session,
            alert_type=ALERT_ADMIN_LOGIN_LOCKED,
            severity=AlertSeverity.WARNING,
            message=(
                f"บัญชีแอดมิน {admin.username} ใส่รหัสผิด {MAX_FAILED_LOGINS} ครั้ง "
                f"ถูกล็อก {int(LOCKOUT_DURATION.total_seconds() // 60)} นาที "
                "ถ้าไม่ใช่เจ้าของบัญชีลองเอง อาจมีคนพยายามเดารหัส"
            ),
            payload={"admin_id": admin.id, "locked_until": admin.locked_until.isoformat()},
            dedup_key=f"{ALERT_ADMIN_LOGIN_LOCKED}:{admin.id}",
        )
    await session.flush()


async def resolve_admin_session(
    session: AsyncSession,
    token: str,
    now: datetime,
) -> AdminUser | None:
    statement = (
        sa.select(AdminUser)
        .join(AdminSession, AdminSession.admin_user_id == AdminUser.id)
        .where(
            AdminSession.token_hash == hash_session_token(token),
            AdminSession.revoked_at.is_(None),
            AdminSession.expires_at > now,
            AdminUser.is_active.is_(True),
        )
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def revoke_admin_session(
    session: AsyncSession,
    token: str,
    now: datetime,
) -> bool:
    statement = (
        sa.update(AdminSession)
        .where(
            AdminSession.token_hash == hash_session_token(token),
            AdminSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
        .returning(AdminSession.admin_user_id)
    )
    admin_user_id = (await session.execute(statement)).scalar_one_or_none()
    if admin_user_id is not None:
        logger.info("admin session revoked: admin_id=%s", admin_user_id)
    return admin_user_id is not None


async def revoke_all_admin_sessions(
    session: AsyncSession,
    admin_user_id: int,
    now: datetime,
) -> int:
    statement = (
        sa.update(AdminSession)
        .where(
            AdminSession.admin_user_id == admin_user_id,
            AdminSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    revoked = (await session.execute(statement)).rowcount
    logger.info(
        "admin sessions revoked: admin_id=%s count=%s", admin_user_id, revoked
    )
    return revoked


async def create_admin(
    session: AsyncSession,
    username: str,
    password: str,
) -> AdminUser:
    username = normalize_username(username)
    if not username:
        raise ValueError("username must not be empty")
    if await find_admin_by_username(session, username) is not None:
        raise AdminUserExistsError(username)

    admin = AdminUser(username=username, password_hash=await hash_password(password))
    session.add(admin)
    await session.flush()
    logger.info("admin created: admin_id=%s username=%s", admin.id, admin.username)
    return admin


async def set_admin_password(
    session: AsyncSession,
    username: str,
    password: str,
    now: datetime,
) -> AdminUser:
    admin = await find_admin_by_username(session, username, for_update=True)
    if admin is None:
        raise AdminUserNotFoundError(username)

    admin.password_hash = await hash_password(password)
    admin.failed_login_count = 0
    admin.locked_until = None
    await revoke_all_admin_sessions(session, admin.id, now)
    await session.flush()
    logger.info("admin password changed: admin_id=%s", admin.id)
    return admin


async def set_admin_active(
    session: AsyncSession,
    username: str,
    active: bool,
    now: datetime,
) -> AdminUser:
    admin = await find_admin_by_username(session, username, for_update=True)
    if admin is None:
        raise AdminUserNotFoundError(username)

    admin.is_active = active
    if not active:
        await revoke_all_admin_sessions(session, admin.id, now)
    await session.flush()
    logger.info("admin active changed: admin_id=%s is_active=%s", admin.id, active)
    return admin


async def list_admins(session: AsyncSession) -> list[AdminUser]:
    statement = sa.select(AdminUser).order_by(AdminUser.id)
    return list((await session.execute(statement)).scalars().all())
