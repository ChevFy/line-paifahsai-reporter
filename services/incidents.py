from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.ext.asyncio import AsyncSession

from models import ACTIVE_INCIDENT_STATUSES, Incident, IncidentStatus, Report


@dataclass(frozen=True)
class ActiveIncident:
    id: int
    latitude: float
    longitude: float
    district_code: str
    status: IncidentStatus
    report_count: int
    created_at: datetime


@dataclass(frozen=True)
class ActiveIncidentList:
    incidents: list[ActiveIncident]
    truncated: bool


async def list_active_incidents(
    session: AsyncSession,
    district_code: str | None,
    limit: int,
) -> ActiveIncidentList:
    point = sa.cast(Incident.location, Geometry(geometry_type="POINT", srid=4326))
    report_count = (
        sa.select(sa.func.count(Report.id))
        .where(Report.incident_id == Incident.id)
        .scalar_subquery()
    )
    statement = (
        sa.select(
            Incident.id,
            sa.func.ST_Y(point).label("latitude"),
            sa.func.ST_X(point).label("longitude"),
            Incident.district_code,
            Incident.status,
            report_count.label("report_count"),
            Incident.created_at,
        )
        .where(Incident.status.in_(ACTIVE_INCIDENT_STATUSES))
        .order_by(Incident.created_at.desc(), Incident.id.desc())
        .limit(limit + 1)
    )
    if district_code is not None:
        statement = statement.where(Incident.district_code == district_code)

    rows = (await session.execute(statement)).all()
    incidents = [ActiveIncident(**row._mapping) for row in rows[:limit]]
    return ActiveIncidentList(incidents=incidents, truncated=len(rows) > limit)
