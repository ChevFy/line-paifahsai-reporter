from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base, str_enum


class VolunteerStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class Volunteer(Base):
    __tablename__ = "volunteers"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    line_user_id: Mapped[str] = mapped_column(
        sa.ForeignKey("line_users.user_id"), unique=True
    )
    full_name: Mapped[str] = mapped_column(sa.String(200))
    phone: Mapped[str] = mapped_column(sa.String(20))
    district_code: Mapped[str] = mapped_column(
        sa.ForeignKey("districts.code"), index=True
    )
    status: Mapped[VolunteerStatus] = mapped_column(
        str_enum(VolunteerStatus, "volunteer_status"),
        server_default=VolunteerStatus.PENDING.value,
    )
    approved_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)

    __table_args__ = (
        sa.CheckConstraint(
            "status <> 'approved' OR approved_at IS NOT NULL",
            name="approved_has_approved_at",
        ),
    )
