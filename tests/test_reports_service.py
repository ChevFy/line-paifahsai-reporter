import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from geoalchemy2 import WKTElement
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from models import (
    AdminAlert,
    Base,
    District,
    Incident,
    IncidentEvent,
    IncidentStatus,
    LineUser,
    Report,
)
from services.ops_date import ops_date_for
from services.reports import (
    ALERT_INCIDENT_NEEDS_DISPATCH,
    ALERT_REPORT_ON_CLOSED_INCIDENT,
    ReporterBlockedError,
    ReportOutcome,
    ReportSubmission,
    UnknownDistrictError,
    submit_report,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="TEST_DATABASE_URL not set (needs PostgreSQL + PostGIS)",
    ),
]

PAI = "5803"
BASE_LAT = 19.36
BASE_LON = 98.44
DEGREES_LAT_PER_METER = 1 / 110_700
NOW = datetime(2026, 3, 2, 3, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def schema():
    engine = sa.create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)
    yield engine
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
    engine.dispose()


@pytest.fixture
async def sessionmaker(schema):
    with schema.begin() as connection:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        connection.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        connection.execute(
            sa.insert(District).values(
                code=PAI, name_th="ปาย", province_name_th="แม่ฮ่องสอน"
            )
        )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def submission(
    north_meters: float = 0,
    user_id: str = "U1",
    district_code: str = PAI,
    client_request_id: uuid.UUID | None = None,
) -> ReportSubmission:
    return ReportSubmission(
        reporter_user_id=user_id,
        reporter_display_name="Somchai",
        client_request_id=client_request_id or uuid.uuid4(),
        latitude=BASE_LAT + north_meters * DEGREES_LAT_PER_METER,
        longitude=BASE_LON,
        district_code=district_code,
        description="เห็นควัน",
    )


async def submit(sessionmaker, data: ReportSubmission, now: datetime = NOW):
    async with sessionmaker() as session, session.begin():
        return await submit_report(session, data, now)


async def add_incident(
    sessionmaker,
    status: IncidentStatus,
    closed_ago: timedelta | None = None,
    north_meters: float = 0,
) -> int:
    lat = BASE_LAT + north_meters * DEGREES_LAT_PER_METER
    incident = Incident(
        location=WKTElement(f"SRID=4326;POINT({BASE_LON} {lat})", extended=True),
        district_code=PAI,
        status=status,
        ops_date=ops_date_for(NOW),
        closed_at=NOW - closed_ago if closed_ago is not None else None,
    )
    async with sessionmaker() as session, session.begin():
        session.add(incident)
        await session.flush()
        return incident.id


async def scalar(sessionmaker, statement):
    async with sessionmaker() as session:
        return (await session.execute(statement)).scalar_one()


async def alert_types(sessionmaker) -> list[str]:
    async with sessionmaker() as session:
        rows = await session.execute(
            sa.select(AdminAlert.alert_type).order_by(AdminAlert.id)
        )
        return list(rows.scalars())


async def test_first_report_creates_incident_and_alerts_admin(sessionmaker):
    result = await submit(sessionmaker, submission())

    assert result.outcome == ReportOutcome.NEW_INCIDENT
    assert await alert_types(sessionmaker) == [ALERT_INCIDENT_NEEDS_DISPATCH]
    assert await scalar(sessionmaker, sa.select(LineUser.report_count)) == 1
    assert (
        await scalar(sessionmaker, sa.select(IncidentEvent.event_type))
        == "incident_created"
    )


async def test_report_within_radius_merges(sessionmaker):
    first = await submit(sessionmaker, submission())
    second = await submit(sessionmaker, submission(north_meters=950, user_id="U2"))

    assert second.outcome == ReportOutcome.MERGED
    assert second.incident_id == first.incident_id
    assert await alert_types(sessionmaker) == [ALERT_INCIDENT_NEEDS_DISPATCH]


async def test_report_outside_radius_creates_new_incident(sessionmaker):
    first = await submit(sessionmaker, submission())
    second = await submit(sessionmaker, submission(north_meters=1100, user_id="U2"))

    assert second.outcome == ReportOutcome.NEW_INCIDENT
    assert second.incident_id != first.incident_id


async def test_same_client_request_id_is_idempotent(sessionmaker):
    request_id = uuid.uuid4()
    first = await submit(sessionmaker, submission(client_request_id=request_id))
    second = await submit(sessionmaker, submission(client_request_id=request_id))

    assert second.outcome == ReportOutcome.DUPLICATE_REQUEST
    assert second.report_id == first.report_id
    assert await scalar(sessionmaker, sa.select(sa.func.count(Report.id))) == 1
    assert await scalar(sessionmaker, sa.select(LineUser.report_count)) == 1


async def test_recently_closed_incident_is_merged_and_alerted(sessionmaker):
    incident_id = await add_incident(
        sessionmaker, IncidentStatus.CLOSED, closed_ago=timedelta(hours=5, minutes=59)
    )

    result = await submit(sessionmaker, submission())

    assert result.outcome == ReportOutcome.MERGED_RECENTLY_CLOSED
    assert result.incident_id == incident_id
    assert await alert_types(sessionmaker) == [ALERT_REPORT_ON_CLOSED_INCIDENT]
    status = await scalar(
        sessionmaker, sa.select(Incident.status).where(Incident.id == incident_id)
    )
    assert status == IncidentStatus.CLOSED


async def test_incident_closed_beyond_window_is_new_incident(sessionmaker):
    incident_id = await add_incident(
        sessionmaker, IncidentStatus.CLOSED, closed_ago=timedelta(hours=6, minutes=1)
    )

    result = await submit(sessionmaker, submission())

    assert result.outcome == ReportOutcome.NEW_INCIDENT
    assert result.incident_id != incident_id


async def test_active_incident_preferred_over_closer_closed_one(sessionmaker):
    await add_incident(sessionmaker, IncidentStatus.CLOSED, closed_ago=timedelta(hours=1))
    active_id = await add_incident(
        sessionmaker, IncidentStatus.IN_PROGRESS, north_meters=500
    )

    result = await submit(sessionmaker, submission())

    assert result.outcome == ReportOutcome.MERGED
    assert result.incident_id == active_id


async def test_false_alarm_incident_is_not_matched(sessionmaker):
    false_alarm_id = await add_incident(
        sessionmaker, IncidentStatus.FALSE_ALARM, closed_ago=timedelta(minutes=30)
    )

    result = await submit(sessionmaker, submission())

    assert result.outcome == ReportOutcome.NEW_INCIDENT
    assert result.incident_id != false_alarm_id


async def test_unknown_district_rolls_back(sessionmaker):
    with pytest.raises(UnknownDistrictError):
        await submit(sessionmaker, submission(district_code="9999"))

    assert await scalar(sessionmaker, sa.select(sa.func.count(Report.id))) == 0


async def test_blocked_reporter_is_rejected(sessionmaker):
    async with sessionmaker() as session, session.begin():
        session.add(LineUser(user_id="U1", is_blocked=True))

    with pytest.raises(ReporterBlockedError):
        await submit(sessionmaker, submission())

    assert await scalar(sessionmaker, sa.select(sa.func.count(Report.id))) == 0


async def test_concurrent_reports_at_same_spot_create_one_incident(sessionmaker):
    results = await asyncio.gather(
        *(submit(sessionmaker, submission(user_id=f"U{i}")) for i in range(5))
    )

    outcomes = sorted(result.outcome for result in results)
    assert outcomes.count(ReportOutcome.NEW_INCIDENT) == 1
    assert outcomes.count(ReportOutcome.MERGED) == 4
    assert len({result.incident_id for result in results}) == 1
    assert await scalar(sessionmaker, sa.select(sa.func.count(Incident.id))) == 1
