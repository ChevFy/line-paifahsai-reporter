import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import AdminAlert, AlertSeverity

logger = logging.getLogger(__name__)


async def record_admin_alert(
    session: AsyncSession,
    alert_type: str,
    severity: AlertSeverity,
    message: str,
    payload: dict[str, Any] | None = None,
    dedup_key: str | None = None,
) -> int:
    statement = insert(AdminAlert).values(
        alert_type=alert_type,
        severity=severity,
        message=message,
        payload=payload or {},
        dedup_key=dedup_key,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[AdminAlert.dedup_key],
        set_={
            "severity": statement.excluded.severity,
            "message": statement.excluded.message,
            "payload": statement.excluded.payload,
            "occurrence_count": AdminAlert.occurrence_count + 1,
            "last_occurred_at": func.now(),
            "acknowledged_at": None,
            "acknowledged_by": None,
        },
    ).returning(AdminAlert.id, AdminAlert.occurrence_count)

    alert_id, occurrence_count = (await session.execute(statement)).one()

    logger.info(
        "admin alert recorded: id=%s alert_type=%s severity=%s occurrence_count=%s",
        alert_id,
        alert_type,
        severity,
        occurrence_count,
    )
    return alert_id


async def acknowledge_admin_alert(
    session: AsyncSession,
    dedup_key: str,
    acknowledged_by: str,
    now: datetime,
) -> bool:
    statement = (
        update(AdminAlert)
        .where(AdminAlert.dedup_key == dedup_key, AdminAlert.acknowledged_at.is_(None))
        .values(acknowledged_at=now, acknowledged_by=acknowledged_by[:100])
        .returning(AdminAlert.id)
    )
    alert_id = (await session.execute(statement)).scalar_one_or_none()
    if alert_id is not None:
        logger.info(
            "admin alert acknowledged: id=%s dedup_key=%s by=%s",
            alert_id,
            dedup_key,
            acknowledged_by,
        )
    return alert_id is not None
