from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    ops_date: Mapped[date] = mapped_column(unique=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    narrative: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)
    sent_at: Mapped[datetime | None]
