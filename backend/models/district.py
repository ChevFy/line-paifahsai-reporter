import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class District(Base):
    __tablename__ = "districts"

    code: Mapped[str] = mapped_column(sa.String(4), primary_key=True)
    name_th: Mapped[str] = mapped_column(sa.String(100))
    province_name_th: Mapped[str] = mapped_column(sa.String(100))

    __table_args__ = (
        sa.CheckConstraint("code ~ '^[0-9]{4}$'", name="code_format"),
    )
