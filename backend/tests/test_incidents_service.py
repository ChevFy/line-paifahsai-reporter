import uuid
from datetime import UTC, datetime

import pytest
from geoalchemy2 import WKTElement

from conftest import MAE_TAENG, PAI, requires_postgis
from models import Incident, IncidentStatus, LineUser, Report
from services.incidents import list_active_incidents
from services.ops_date import ops_date_for

pytestmark = [pytest.mark.anyio, requires_postgis]

NOW = datetime(2026, 3, 2, 3, 0, tzinfo=UTC)


async def add_incident(
    sessionmaker,
    status: IncidentStatus = IncidentStatus.OPEN,
    district_code: str = PAI,
    lat: float = 19.36,
    lon: float = 98.44,
    report_count: int = 0,
) -> int:
    ewkt = f"SRID=4326;POINT({lon} {lat})"
    is_closed = status in (IncidentStatus.CLOSED, IncidentStatus.FALSE_ALARM)
    incident = Incident(
        location=WKTElement(ewkt, extended=True),
        district_code=district_code,
        status=status,
        ops_date=ops_date_for(NOW),
        closed_at=NOW if is_closed else None,
    )
    async with sessionmaker() as session, session.begin():
        await session.merge(LineUser(user_id="U1"))
        session.add(incident)
        await session.flush()
        for _ in range(report_count):
            session.add(
                Report(
                    incident_id=incident.id,
                    reporter_user_id="U1",
                    location=WKTElement(ewkt, extended=True),
                    ops_date=ops_date_for(NOW),
                    client_request_id=uuid.uuid4(),
                )
            )
        return incident.id


async def list_active(sessionmaker, district_code: str | None = None, limit: int = 500):
    async with sessionmaker() as session:
        return await list_active_incidents(session, district_code, limit)


async def test_returns_only_open_and_in_progress(sessionmaker):
    open_id = await add_incident(sessionmaker, IncidentStatus.OPEN)
    in_progress_id = await add_incident(sessionmaker, IncidentStatus.IN_PROGRESS)
    await add_incident(sessionmaker, IncidentStatus.CLOSED)
    await add_incident(sessionmaker, IncidentStatus.FALSE_ALARM)

    result = await list_active(sessionmaker)

    assert {incident.id for incident in result.incidents} == {open_id, in_progress_id}
    assert result.truncated is False


async def test_returns_coordinates_and_report_count(sessionmaker):
    await add_incident(sessionmaker, lat=19.123456, lon=98.654321, report_count=3)

    [incident] = (await list_active(sessionmaker)).incidents

    assert incident.latitude == pytest.approx(19.123456)
    assert incident.longitude == pytest.approx(98.654321)
    assert incident.report_count == 3
    assert incident.status == IncidentStatus.OPEN


async def test_filters_by_district(sessionmaker):
    pai_id = await add_incident(sessionmaker, district_code=PAI)
    await add_incident(sessionmaker, district_code=MAE_TAENG)

    result = await list_active(sessionmaker, district_code=PAI)

    assert [incident.id for incident in result.incidents] == [pai_id]


async def test_marks_truncated_when_over_limit(sessionmaker):
    for _ in range(3):
        await add_incident(sessionmaker)

    result = await list_active(sessionmaker, limit=2)

    assert len(result.incidents) == 2
    assert result.truncated is True
