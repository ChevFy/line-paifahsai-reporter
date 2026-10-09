from datetime import datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base, str_enum


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    job_type: Mapped[str] = mapped_column(sa.String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa.text("'{}'::jsonb")
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(200), unique=True)
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "job_status"),
        server_default=JobStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(server_default="0")
    max_attempts: Mapped[int] = mapped_column(server_default="5")
    run_at: Mapped[datetime] = mapped_column(server_default=NOW)
    locked_at: Mapped[datetime | None]
    locked_by: Mapped[str | None] = mapped_column(sa.String(100))
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(server_default=NOW, onupdate=NOW)
    finished_at: Mapped[datetime | None]

    __table_args__ = (
        sa.Index("ix_jobs_status_run_at", "status", "run_at"),
        sa.CheckConstraint(
            "status <> 'running' OR locked_at IS NOT NULL",
            name="running_has_locked_at",
        ),
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        sa.CheckConstraint("max_attempts > 0", name="max_attempts_positive"),
    )
