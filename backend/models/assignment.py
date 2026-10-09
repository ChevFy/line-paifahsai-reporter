from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base, str_enum


class AssignmentStatus(StrEnum):
    ACCEPTED = "accepted"
    ARRIVED = "arrived"
    DONE = "done"
    WITHDRAWN = "withdrawn"


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    incident_id: Mapped[int] = mapped_column(sa.ForeignKey("incidents.id"))
    volunteer_id: Mapped[int] = mapped_column(
        sa.ForeignKey("volunteers.id"), index=True
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        str_enum(AssignmentStatus, "assignment_status"),
        server_default=AssignmentStatus.ACCEPTED.value,
    )
    accepted_at: Mapped[datetime] = mapped_column(server_default=NOW)
    completed_at: Mapped[datetime | None]

    __table_args__ = (
        sa.UniqueConstraint("incident_id", "volunteer_id"),
        sa.CheckConstraint(
            "(status = 'done') = (completed_at IS NOT NULL)",
            name="completed_at_matches_status",
        ),
    )
