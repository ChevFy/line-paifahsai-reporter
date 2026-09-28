from datetime import date, datetime

import sqlalchemy as sa
from geoalchemy2 import Geography, WKBElement
from sqlalchemy.orm import Mapped, mapped_column

from models.base import NOW, Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    incident_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("incidents.id"), index=True
    )
    reporter_user_id: Mapped[str] = mapped_column(
        sa.ForeignKey("line_users.user_id"), index=True
    )
    location: Mapped[WKBElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326)
    )
    description: Mapped[str | None] = mapped_column(sa.Text)
    image_path: Mapped[str | None] = mapped_column(sa.String(500))
    ops_date: Mapped[date] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=NOW)
