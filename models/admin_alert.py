from datetime import datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base, str_enum


class AlertSeverity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


class AdminAlert(Base):
    __tablename__ = "admin_alerts"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    alert_type: Mapped[str] = mapped_column(sa.String(50))
    severity: Mapped[AlertSeverity] = mapped_column(
        str_enum(AlertSeverity, "alert_severity")
    )
    message: Mapped[str] = mapped_column(sa.Text)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    dedup_key: Mapped[str | None] = mapped_column(sa.String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)
    acknowledged_at: Mapped[datetime | None]
    acknowledged_by: Mapped[str | None] = mapped_column(sa.String(100))

    __table_args__ = (
        sa.Index(
            "ix_admin_alerts_unacknowledged_created_at",
            "created_at",
            postgresql_where=sa.text("acknowledged_at IS NULL"),
        ),
        sa.CheckConstraint(
            "(acknowledged_at IS NULL) = (acknowledged_by IS NULL)",
            name="acknowledged_pair",
        ),
    )
