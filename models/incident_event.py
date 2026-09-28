from datetime import datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base, str_enum


class ActorType(StrEnum):
    SYSTEM = "system"
    REPORTER = "reporter"
    VOLUNTEER = "volunteer"
    ADMIN = "admin"


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    incident_id: Mapped[int] = mapped_column(sa.ForeignKey("incidents.id"))
    event_type: Mapped[str] = mapped_column(sa.String(50))
    actor_type: Mapped[ActorType] = mapped_column(str_enum(ActorType, "actor_type"))
    actor_id: Mapped[str | None] = mapped_column(sa.String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)

    __table_args__ = (
        sa.Index("ix_incident_events_incident_id_created_at", "incident_id", "created_at"),
    )
