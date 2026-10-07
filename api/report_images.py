import logging

from fastapi import APIRouter, Header, HTTPException, UploadFile

from api.line_auth import authenticate_liff_user
from api.reports import (
    EMERGENCY_NOTICE,
    EMERGENCY_PHONE,
    EmergencyNoticeRoute,
    report_error,
)
from core.alerts import record_admin_alert_safely
from core.db import SessionLocal
from core.storage import StorageUnavailableError, put_object
from models import AlertSeverity
from schemas.report import ReportImageResponse
from services.report_images import (
    ImageOutcome,
    ReportImage,
    detect_image_type,
    save_report_image,
)

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALERT_IMAGE_STORAGE_UNAVAILABLE = "report_image_storage_unavailable"
ALERT_IMAGE_FAILED = "report_image_failed"
REPORT_KEPT_NOTICE = "การแจ้งเหตุของคุณเข้าระบบแล้ว ไม่ต้องแจ้งซ้ำ"
OUTCOME_MESSAGES = {
    ImageOutcome.STORED: "ได้รับรูปแล้ว ขอบคุณครับ",
    ImageOutcome.ALREADY_ATTACHED: "รูปของการแจ้งนี้บันทึกไว้แล้ว",
}

router = APIRouter(route_class=EmergencyNoticeRoute)


@router.post("/reports/{report_id}/image", response_model=ReportImageResponse)
async def upload_report_image(
    report_id: int,
    image: UploadFile,
    authorization: str | None = Header(None),
) -> ReportImageResponse:
    identity = await authenticate_liff_user(authorization, report_error)

    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise report_error(
            413, f"รูปใหญ่เกิน {MAX_IMAGE_BYTES // (1024 * 1024)} MB {REPORT_KEPT_NOTICE}"
        )
    image_type = detect_image_type(data)
    if image_type is None:
        raise report_error(
            415, f"รองรับเฉพาะรูป JPEG, PNG, WEBP, HEIC {REPORT_KEPT_NOTICE}"
        )

    report_image = ReportImage(
        report_id=report_id,
        reporter_user_id=identity.user_id,
        data=data,
        image_type=image_type,
    )
    payload = {
        "report_id": report_id,
        "user_id": identity.user_id,
        "bytes": len(data),
    }

    try:
        outcome = await save_report_image(SessionLocal, put_object, report_image)
    except StorageUnavailableError as error:
        logger.error(
            "image storage unavailable: report_id=%s user_id=%s error=%s",
            report_id,
            identity.user_id,
            error,
        )
        await record_admin_alert_safely(
            alert_type=ALERT_IMAGE_STORAGE_UNAVAILABLE,
            severity=AlertSeverity.WARNING,
            message=(
                "ที่เก็บรูปใช้งานไม่ได้ รูปจากผู้แจ้งไม่ถูกบันทึก "
                "การแจ้งเหตุและการส่งหาจิตอาสายังทำงานปกติ ตรวจ S3/SeaweedFS"
            ),
            payload={**payload, "error": str(error)},
            dedup_key=ALERT_IMAGE_STORAGE_UNAVAILABLE,
        )
        raise report_error(503, f"บันทึกรูปไม่สำเร็จ {REPORT_KEPT_NOTICE}")
    except Exception as error:
        logger.exception(
            "failed to save report image: report_id=%s user_id=%s",
            report_id,
            identity.user_id,
        )
        await record_admin_alert_safely(
            alert_type=ALERT_IMAGE_FAILED,
            severity=AlertSeverity.WARNING,
            message="ระบบบันทึกรูปการแจ้งเหตุไม่สำเร็จ การแจ้งเหตุยังเข้าระบบปกติ",
            payload={**payload, "error": f"{type(error).__name__}: {error}"},
            dedup_key=ALERT_IMAGE_FAILED,
        )
        raise report_error(500, f"บันทึกรูปไม่สำเร็จ {REPORT_KEPT_NOTICE}")

    if outcome == ImageOutcome.REPORT_NOT_FOUND:
        raise report_error(404, "ไม่พบการแจ้งเหตุนี้")

    return ReportImageResponse(
        report_id=report_id,
        outcome=outcome,
        message=f"{OUTCOME_MESSAGES[outcome]}\n{EMERGENCY_NOTICE}",
        emergency_phone=EMERGENCY_PHONE,
    )
