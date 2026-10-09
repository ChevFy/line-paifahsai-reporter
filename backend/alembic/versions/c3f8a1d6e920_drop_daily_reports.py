"""drop daily_reports

Revision ID: c3f8a1d6e920
Revises: b7e3c9a2d415
Create Date: 2026-10-09 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "c3f8a1d6e920"
down_revision: str | Sequence[str] | None = "b7e3c9a2d415"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.drop_table("daily_reports")


def downgrade() -> None:
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ops_date", sa.Date(), nullable=False),
        sa.Column("metrics", JSONB(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("sent_at", TIMESTAMPTZ, nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_reports")),
        sa.UniqueConstraint("ops_date", name=op.f("uq_daily_reports_ops_date")),
    )
