"""add admin_users and admin_sessions

Revision ID: a4d2e8f61c37
Revises: 5c1a7e3b9f42
Create Date: 2026-10-08 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a4d2e8f61c37"
down_revision: str | Sequence[str] | None = "5c1a7e3b9f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "failed_login_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("locked_until", TIMESTAMPTZ, nullable=True),
        sa.Column("last_login_at", TIMESTAMPTZ, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "username = lower(username)",
            name=op.f("ck_admin_users_username_lowercase"),
        ),
        sa.CheckConstraint(
            "failed_login_count >= 0",
            name=op.f("ck_admin_users_failed_login_count_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_users")),
        sa.UniqueConstraint("username", name=op.f("uq_admin_users_username")),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("admin_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("expires_at", TIMESTAMPTZ, nullable=False),
        sa.Column("revoked_at", TIMESTAMPTZ, nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.id"],
            name=op.f("fk_admin_sessions_admin_user_id_admin_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_admin_sessions_token_hash")),
    )
    op.create_index(
        op.f("ix_admin_sessions_admin_user_id"),
        "admin_sessions",
        ["admin_user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_sessions_admin_user_id"), table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_table("admin_users")
