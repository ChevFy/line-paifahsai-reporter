from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base


class LineUser(Base):
    __tablename__ = "line_users"

    user_id: Mapped[str] = mapped_column(sa.String(33), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(sa.String(100))
    report_count: Mapped[int] = mapped_column(server_default="0")
    false_report_count: Mapped[int] = mapped_column(server_default="0")
    is_blocked: Mapped[bool] = mapped_column(server_default=sa.false())
    first_seen_at: Mapped[datetime] = mapped_column(server_default=NOW)
