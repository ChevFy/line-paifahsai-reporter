import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from core.db import SessionLocal
from models import AdminUser
from schemas.admin import AdminLogin, AdminResponse
from services.admin_auth import (
    LoginOutcome,
    login_admin,
    resolve_admin_session,
    revoke_admin_session,
)

logger = logging.getLogger(__name__)

SESSION_COOKIE = "admin_session"
COOKIE_PATH = "/admin"
LOGIN_FAILED_MESSAGE = (
    "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง หรือบัญชีถูกล็อกชั่วคราวจากการใส่รหัสผิดหลายครั้ง"
)
AUTH_REQUIRED_MESSAGE = "กรุณาเข้าสู่ระบบแอดมิน"

router = APIRouter(prefix="/admin")


def auth_required_error() -> HTTPException:
    return HTTPException(status_code=401, detail={"message": AUTH_REQUIRED_MESSAGE})


async def require_admin(
    admin_session: str | None = Cookie(None),
) -> AdminUser:
    if not admin_session:
        raise auth_required_error()

    async with SessionLocal() as session:
        admin = await resolve_admin_session(session, admin_session, datetime.now(UTC))
    if admin is None:
        raise auth_required_error()
    return admin


@router.post("/login", response_model=AdminResponse)
async def login(body: AdminLogin, response: Response) -> AdminResponse:
    async with SessionLocal() as session, session.begin():
        result = await login_admin(
            session, body.username, body.password, datetime.now(UTC)
        )

    if result.outcome != LoginOutcome.SUCCESS:
        raise HTTPException(status_code=401, detail={"message": LOGIN_FAILED_MESSAGE})

    response.set_cookie(
        SESSION_COOKIE,
        result.session_token,
        expires=result.expires_at,
        path=COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return AdminResponse.model_validate(result.admin)


@router.post("/logout", status_code=204)
async def logout(admin_session: str | None = Cookie(None)) -> Response:
    if admin_session:
        async with SessionLocal() as session, session.begin():
            await revoke_admin_session(session, admin_session, datetime.now(UTC))

    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE,
        path=COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return response


CurrentAdmin = Annotated[AdminUser, Depends(require_admin)]


@router.get("/me", response_model=AdminResponse)
async def me(admin: CurrentAdmin) -> AdminResponse:
    return AdminResponse.model_validate(admin)
