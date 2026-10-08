"""add incidents.public_id

Revision ID: b7e3c9a2d415
Revises: a4d2e8f61c37
Create Date: 2026-10-09 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e3c9a2d415"
down_revision: str | Sequence[str] | None = "a4d2e8f61c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column(
            "public_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        op.f("uq_incidents_public_id"), "incidents", ["public_id"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_incidents_public_id"), "incidents", type_="unique")
    op.drop_column("incidents", "public_id")
