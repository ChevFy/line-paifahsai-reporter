from datetime import date, datetime
from enum import StrEnum

import sqlalchemy as sa
from geoalchemy2 import Geography, WKBElement
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base, str_enum


class IncidentStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    FALSE_ALARM = "false_alarm"


ACTIVE_INCIDENT_STATUSES = (IncidentStatus.OPEN, IncidentStatus.IN_PROGRESS)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    location: Mapped[WKBElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326)
    )
    description: Mapped[str | None] = mapped_column(sa.Text)
    district_code: Mapped[str] = mapped_column(
        sa.ForeignKey("districts.code"), index=True
    )
    status: Mapped[IncidentStatus] = mapped_column(
        str_enum(IncidentStatus, "incident_status"),
        server_default=IncidentStatus.OPEN.value,
    )
    ops_date: Mapped[date]
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)
    closed_at: Mapped[datetime | None]

    __table_args__ = (
        sa.Index("ix_incidents_status_closed_at", "status", "closed_at"),
        sa.Index("ix_incidents_ops_date", "ops_date"),
        sa.CheckConstraint(
            "(status IN ('closed', 'false_alarm')) = (closed_at IS NOT NULL)",
            name="closed_at_matches_status",
        ),
    )
