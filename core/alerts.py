import logging
from typing import Any

from core.db import SessionLocal
from models import AlertSeverity
from services.admin_alerts import record_admin_alert

logger = logging.getLogger(__name__)


async def record_admin_alert_safely(
    alert_type: str,
    severity: AlertSeverity,
    message: str,
    payload: dict[str, Any],
    dedup_key: str | None = None,
) -> None:
    try:
        async with SessionLocal() as session, session.begin():
            await record_admin_alert(
                session,
                alert_type=alert_type,
                severity=severity,
                message=message,
                payload=payload,
                dedup_key=dedup_key,
            )
    except Exception:
        logger.critical(
            "failed to record admin alert: alert_type=%s payload=%s",
            alert_type,
            payload,
            exc_info=True,
        )
