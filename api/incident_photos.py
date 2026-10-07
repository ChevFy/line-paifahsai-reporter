import logging
from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Response
from fastapi.responses import HTMLResponse

from api.report_images import ALERT_IMAGE_STORAGE_UNAVAILABLE
from config.config import settings
from core.alerts import record_admin_alert_safely
from core.db import SessionLocal
from core.storage import (
    StorageObjectNotFoundError,
    StorageUnavailableError,
    get_object,
)
from models import AlertSeverity
from services.incident_photos import (
    LinkStatus,
    find_incident_photo_key,
    link_query,
    list_incident_photos,
    verify_incident_link,
)

logger = logging.getLogger(__name__)

BANGKOK = ZoneInfo("Asia/Bangkok")
ALERT_IMAGE_MISSING = "report_image_missing"
PRIVATE_HEADERS = {
    "Cache-Control": "private, max-age=300",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
LINK_ERRORS = {
    LinkStatus.EXPIRED: (410, "ลิงก์หมดอายุแล้ว"),
    LinkStatus.INVALID: (403, "ลิงก์ไม่ถูกต้อง"),
}
PAGE_STYLE = (
    "body{margin:0;padding:16px;font-family:sans-serif;background:#111;color:#eee}"
    "h1{font-size:18px;margin:0 0 4px}p{color:#aaa;font-size:14px;margin:0 0 16px}"
    "figure{margin:0 0 20px}img{width:100%;border-radius:8px;background:#222}"
    "figcaption{font-size:13px;color:#aaa;margin-top:4px}"
)

router = APIRouter()


def page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="th"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{PAGE_STYLE}</style></head>"
        f"<body><h1>{escape(title)}</h1>{body}</body></html>"
    )
    return HTMLResponse(html, status_code=status_code, headers=PRIVATE_HEADERS)


def check_link(incident_id: int, expires: int, sig: str) -> LinkStatus:
    status = verify_incident_link(
        settings.PHOTO_LINK_SECRET, incident_id, expires, sig, datetime.now(UTC)
    )
    if status != LinkStatus.VALID:
        logger.warning(
            "photo link rejected: incident_id=%s status=%s", incident_id, status
        )
    return status


@router.get("/incidents/{incident_id}/photos", response_class=HTMLResponse)
async def incident_photo_page(
    incident_id: int,
    expires: int = Query(),
    sig: str = Query(),
) -> HTMLResponse:
    status = check_link(incident_id, expires, sig)
    if status != LinkStatus.VALID:
        status_code, text = LINK_ERRORS[status]
        return page(text, "<p>กรุณาเปิดจากข้อความแจ้งเหตุล่าสุด</p>", status_code)

    async with SessionLocal() as session:
        photos = await list_incident_photos(session, incident_id)

    title = f"รูปจากผู้แจ้ง เหตุ #{incident_id}"
    if not photos:
        return page(title, "<p>ยังไม่มีรูปจากผู้แจ้ง ลองเปิดใหม่ภายหลัง</p>")

    query = escape(link_query(settings.PHOTO_LINK_SECRET, incident_id, expires))
    figures = "".join(
        f'<figure><img src="/incidents/{incident_id}/photos/{photo.report_id}?{query}" '
        f'alt="รูปจากผู้แจ้ง" loading="lazy">'
        f"<figcaption>แจ้งเมื่อ "
        f"{photo.created_at.astimezone(BANGKOK):%d/%m %H:%M} น.</figcaption></figure>"
        for photo in photos
    )
    logger.info("photo page viewed: incident_id=%s photos=%s", incident_id, len(photos))
    return page(title, f"<p>{len(photos)} รูป</p>{figures}")


@router.get("/incidents/{incident_id}/photos/{report_id}")
async def incident_photo(
    incident_id: int,
    report_id: int,
    expires: int = Query(),
    sig: str = Query(),
) -> Response:
    status = check_link(incident_id, expires, sig)
    if status != LinkStatus.VALID:
        return Response(status_code=LINK_ERRORS[status][0], headers=PRIVATE_HEADERS)

    async with SessionLocal() as session:
        key = await find_incident_photo_key(session, incident_id, report_id)
    if key is None:
        return Response(status_code=404, headers=PRIVATE_HEADERS)

    payload = {"incident_id": incident_id, "report_id": report_id, "key": key}
    try:
        data, content_type = await get_object(key)
    except StorageObjectNotFoundError:
        logger.error("report image missing in storage: %s", payload)
        await record_admin_alert_safely(
            alert_type=ALERT_IMAGE_MISSING,
            severity=AlertSeverity.WARNING,
            message="รูปที่ DB อ้างถึงไม่มีใน storage อาจถูกลบหรือ bucket ผิด",
            payload=payload,
            dedup_key=f"{ALERT_IMAGE_MISSING}:{report_id}",
        )
        return Response(status_code=404, headers=PRIVATE_HEADERS)
    except StorageUnavailableError as error:
        logger.error("image storage unavailable on read: %s error=%s", payload, error)
        await record_admin_alert_safely(
            alert_type=ALERT_IMAGE_STORAGE_UNAVAILABLE,
            severity=AlertSeverity.WARNING,
            message=(
                "ที่เก็บรูปใช้งานไม่ได้ จิตอาสา/แอดมินเปิดดูรูปไม่ได้ "
                "การแจ้งเหตุและการส่งหาจิตอาสายังทำงานปกติ ตรวจ S3/SeaweedFS"
            ),
            payload={**payload, "error": str(error)},
            dedup_key=ALERT_IMAGE_STORAGE_UNAVAILABLE,
        )
        return Response(status_code=503, headers=PRIVATE_HEADERS)

    return Response(data, media_type=content_type, headers=PRIVATE_HEADERS)
