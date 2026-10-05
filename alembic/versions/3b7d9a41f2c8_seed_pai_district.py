"""seed Pai district

Revision ID: 3b7d9a41f2c8
Revises: cc11e7ccf123
Create Date: 2026-09-30 15:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3b7d9a41f2c8"
down_revision: str | Sequence[str] | None = "cc11e7ccf123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAI_CODE = "5803"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO districts (code, name_th, province_name_th)
            VALUES (:code, :name_th, :province_name_th)
            """
        ).bindparams(
            code=PAI_CODE,
            name_th="ปาย",
            province_name_th="แม่ฮ่องสอน",
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM districts WHERE code = :code").bindparams(code=PAI_CODE)
    )
