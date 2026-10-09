from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(sa.String(100))
    is_active: Mapped[bool] = mapped_column(server_default=sa.true())
    failed_login_count: Mapped[int] = mapped_column(server_default="0")
    locked_until: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)

    __table_args__ = (
        sa.CheckConstraint("username = lower(username)", name="username_lowercase"),
        sa.CheckConstraint(
            "failed_login_count >= 0", name="failed_login_count_non_negative"
        ),
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    admin_user_id: Mapped[int] = mapped_column(
        sa.ForeignKey("admin_users.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
