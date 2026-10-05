import logging
from typing import Any

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
) -> int | None:
    statement = (
        insert(AdminAlert)
        .values(
            alert_type=alert_type,
            severity=severity,
            message=message,
            payload=payload or {},
            dedup_key=dedup_key,
        )
        .on_conflict_do_nothing(index_elements=[AdminAlert.dedup_key])
        .returning(AdminAlert.id)
    )
    alert_id = (await session.execute(statement)).scalar_one_or_none()
    await session.commit()

    if alert_id is None:
        logger.info(
            "admin alert already recorded: alert_type=%s dedup_key=%s",
            alert_type,
            dedup_key,
        )
    else:
        logger.info(
            "admin alert recorded: id=%s alert_type=%s severity=%s",
            alert_id,
            alert_type,
            severity,
        )
    return alert_id
