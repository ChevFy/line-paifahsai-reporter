import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from api.line_auth import authenticate_liff_user
from core.alerts import record_admin_alert_safely
from core.db import SessionLocal
from models import AlertSeverity
from schemas.report import ReportCreate, ReportResponse
from services.reports import (
    ReporterBlockedError,
    ReportOutcome,
    ReportSubmission,
    UnknownDistrictError,
    submit_report,
)

logger = logging.getLogger(__name__)

EMERGENCY_PHONE = "1362"
EMERGENCY_NOTICE = (
    f"หากไฟลุกลามหรือเป็นเหตุด่วน โทร {EMERGENCY_PHONE} (ศูนย์รับแจ้งไฟป่า) ทันที"
)
OUTCOME_MESSAGES = {
    ReportOutcome.NEW_INCIDENT: "ได้รับแจ้งเหตุแล้ว ขอบคุณที่แจ้ง",
    ReportOutcome.MERGED: (
        "ได้รับแจ้งเหตุแล้ว จุดนี้มีผู้แจ้งเข้ามาก่อนหน้า "
        "ข้อมูลของคุณถูกรวมเข้ากับเหตุเดิม"
    ),
    ReportOutcome.MERGED_RECENTLY_CLOSED: (
        "ได้รับแจ้งเหตุแล้ว จุดนี้เพิ่งปิดเหตุไปไม่นาน "
        "ระบบแจ้งแอดมินให้ตรวจสอบว่าไฟปะทุซ้ำหรือไม่"
    ),
    ReportOutcome.DUPLICATE_REQUEST: "ระบบได้รับการแจ้งนี้ไปแล้ว",
}
ALERT_REPORT_FAILED = "report_submit_failed"
ALERT_BLOCKED_REPORTER = "blocked_reporter_attempt"


def emergency_detail(message: str) -> dict:
    return {
        "message": f"{message}\n{EMERGENCY_NOTICE}",
        "emergency_phone": EMERGENCY_PHONE,
    }


def report_error(status_code: int, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=emergency_detail(message))


class EmergencyNoticeRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as error:
                logger.warning("invalid report payload: errors=%s", error.errors())
                detail = emergency_detail(
                    "ข้อมูลการแจ้งเหตุไม่ถูกต้อง กรุณาตรวจสอบหมุดและอำเภอ"
                )
                detail["errors"] = jsonable_encoder(error.errors())
                return JSONResponse(status_code=422, content={"detail": detail})

        return handle


router = APIRouter(route_class=EmergencyNoticeRoute)


@router.post("/reports", response_model=ReportResponse)
async def create_report(
    body: ReportCreate,
    authorization: str | None = Header(None),
) -> ReportResponse:
    identity = await authenticate_liff_user(authorization, report_error)

    submission = ReportSubmission(
        reporter_user_id=identity.user_id,
        reporter_display_name=identity.display_name,
        client_request_id=body.client_request_id,
        latitude=body.latitude,
        longitude=body.longitude,
        district_code=body.district_code,
        description=body.description,
    )

    try:
        async with SessionLocal() as session, session.begin():
            result = await submit_report(session, submission, datetime.now(UTC))
    except UnknownDistrictError:
        logger.warning("unknown district_code=%s", body.district_code)
        raise report_error(422, "ไม่พบอำเภอที่เลือก กรุณาเลือกอำเภอใหม่")
    except ReporterBlockedError:
        logger.warning("blocked reporter attempted report: user_id=%s", identity.user_id)
        await record_admin_alert_safely(
            alert_type=ALERT_BLOCKED_REPORTER,
            severity=AlertSeverity.WARNING,
            message="ผู้ใช้ที่ถูกระงับพยายามแจ้งเหตุ กรุณาตรวจสอบว่าเป็นเหตุจริงหรือไม่",
            payload=submission_payload(submission),
            dedup_key=f"{ALERT_BLOCKED_REPORTER}:{submission.client_request_id}",
        )
        raise report_error(403, "บัญชีนี้ถูกระงับการแจ้งเหตุผ่านระบบนี้")
    except Exception as error:
        logger.exception(
            "failed to submit report: user_id=%s client_request_id=%s",
            identity.user_id,
            body.client_request_id,
        )
        await record_admin_alert_safely(
            alert_type=ALERT_REPORT_FAILED,
            severity=AlertSeverity.CRITICAL,
            message="ระบบบันทึกการแจ้งเหตุไม่สำเร็จ ผู้แจ้งอาจเห็นไฟอยู่ กรุณาติดต่อกลับ",
            payload={**submission_payload(submission), "error": type(error).__name__},
            dedup_key=f"{ALERT_REPORT_FAILED}:{submission.client_request_id}",
        )
        raise report_error(500, "ระบบบันทึกการแจ้งเหตุไม่สำเร็จ")

    return ReportResponse(
        report_id=result.report_id,
        incident_id=result.incident_id,
        outcome=result.outcome,
        message=f"{OUTCOME_MESSAGES[result.outcome]}\n{EMERGENCY_NOTICE}",
        emergency_phone=EMERGENCY_PHONE,
    )


def submission_payload(submission: ReportSubmission) -> dict:
    return {
        "user_id": submission.reporter_user_id,
        "client_request_id": str(submission.client_request_id),
        "latitude": submission.latitude,
        "longitude": submission.longitude,
        "district_code": submission.district_code,
    }
