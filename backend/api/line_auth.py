import logging
from collections.abc import Callable

from fastapi import HTTPException

from core.alerts import record_admin_alert_safely
from line.line_id_token import (
    IdTokenConfigError,
    IdTokenVerificationUnavailableError,
    InvalidIdTokenError,
    LineIdentity,
    verify_id_token,
)
from models import AlertSeverity

logger = logging.getLogger(__name__)

ALERT_ID_TOKEN_UNAVAILABLE = "id_token_verify_unavailable"
ALERT_ID_TOKEN_CONFIG = "id_token_config_error"
AUTH_FAILED_MESSAGE = "ยืนยันตัวตน LINE ไม่สำเร็จ กรุณาเปิดฟอร์มจาก LINE ใหม่"
AUTH_UNAVAILABLE_MESSAGE = "ระบบยืนยันตัวตนขัดข้องชั่วคราว กรุณาลองส่งอีกครั้ง"

ErrorFactory = Callable[[int, str], HTTPException]


def plain_error(status_code: int, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"message": message})


async def authenticate_liff_user(
    authorization: str | None,
    make_error: ErrorFactory = plain_error,
) -> LineIdentity:
    scheme, _, id_token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not id_token:
        raise make_error(401, AUTH_FAILED_MESSAGE)

    try:
        return await verify_id_token(id_token)
    except InvalidIdTokenError as error:
        logger.warning("invalid LIFF id token: %s", error)
        raise make_error(401, AUTH_FAILED_MESSAGE)
    except IdTokenConfigError as error:
        logger.critical("LIFF id token rejected by channel config: %s", error)
        await record_admin_alert_safely(
            alert_type=ALERT_ID_TOKEN_CONFIG,
            severity=AlertSeverity.CRITICAL,
            message=(
                "LINE ปฏิเสธ ID token เพราะ channel ไม่ตรง ผู้แจ้งทุกคนส่งเหตุไม่ได้ "
                "ตรวจ LINE_LOGIN_CHANNEL_ID ให้ตรงกับ LINE Login channel ของ LIFF"
            ),
            payload={"error": str(error)},
            dedup_key=ALERT_ID_TOKEN_CONFIG,
        )
        raise make_error(503, AUTH_UNAVAILABLE_MESSAGE)
    except IdTokenVerificationUnavailableError as error:
        logger.error("LIFF id token verification unavailable: %s", error)
        await record_admin_alert_safely(
            alert_type=ALERT_ID_TOKEN_UNAVAILABLE,
            severity=AlertSeverity.CRITICAL,
            message=(
                "ยืนยัน ID token กับ LINE ไม่ได้ ผู้แจ้งส่งเหตุผ่านฟอร์มไม่ได้ "
                "จนกว่า LINE จะกลับมา ผู้แจ้งอาจกำลังเห็นไฟอยู่"
            ),
            payload={"error": str(error)},
            dedup_key=ALERT_ID_TOKEN_UNAVAILABLE,
        )
        raise make_error(503, AUTH_UNAVAILABLE_MESSAGE)
