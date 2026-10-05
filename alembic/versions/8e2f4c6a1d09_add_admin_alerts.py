"""add admin_alerts

Revision ID: 8e2f4c6a1d09
Revises: 3b7d9a41f2c8
Create Date: 2026-10-05 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "8e2f4c6a1d09"
down_revision: str | Sequence[str] | None = "3b7d9a41f2c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")
EMPTY_JSONB = sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "admin_alerts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "warning",
                "critical",
                name="alert_severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("dedup_key", sa.String(200), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("last_occurred_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("acknowledged_at", TIMESTAMPTZ, nullable=True),
        sa.Column("acknowledged_by", sa.String(100), nullable=True),
        sa.CheckConstraint(
            "(acknowledged_at IS NULL) = (acknowledged_by IS NULL)",
            name=op.f("ck_admin_alerts_acknowledged_pair"),
        ),
        sa.CheckConstraint(
            "occurrence_count > 0",
            name=op.f("ck_admin_alerts_occurrence_count_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_alerts")),
        sa.UniqueConstraint("dedup_key", name=op.f("uq_admin_alerts_dedup_key")),
    )
    op.create_index(
        "ix_admin_alerts_unacknowledged_last_occurred_at",
        "admin_alerts",
        ["last_occurred_at"],
        postgresql_where=sa.text("acknowledged_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_alerts_unacknowledged_last_occurred_at",
        table_name="admin_alerts",
    )
    op.drop_table("admin_alerts")
