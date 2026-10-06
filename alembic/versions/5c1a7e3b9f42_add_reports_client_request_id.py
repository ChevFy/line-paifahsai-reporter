"""add reports.client_request_id

Revision ID: 5c1a7e3b9f42
Revises: 8e2f4c6a1d09
Create Date: 2026-10-05 21:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5c1a7e3b9f42"
down_revision: str | Sequence[str] | None = "8e2f4c6a1d09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("client_request_id", sa.Uuid(), nullable=False))
    op.create_unique_constraint(
        op.f("uq_reports_reporter_user_id_client_request_id"),
        "reports",
        ["reporter_user_id", "client_request_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_reports_reporter_user_id_client_request_id"),
        "reports",
        type_="unique",
    )
    op.drop_column("reports", "client_request_id")
