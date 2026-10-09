from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import District


async def list_districts(session: AsyncSession) -> Sequence[District]:
    statement = sa.select(District).order_by(District.province_name_th, District.name_th)
    return (await session.execute(statement)).scalars().all()
