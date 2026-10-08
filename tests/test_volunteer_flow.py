import asyncio
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from geoalchemy2 import WKTElement

from conftest import MAE_TAENG, PAI, requires_postgis
from jobs import common as jobs_common
from jobs import dispatch as dispatch_job
from models import (
    AdminAlert,
    Assignment,
    Incident,
    IncidentEvent,
    IncidentStatus,
    LineUser,
    Volunteer,
    VolunteerStatus,
)
from services.assignments import AcceptOutcome, accept_incident
from services.dispatch import ALERT_NO_VOLUNTEERS, EVENT_DISPATCHED
from services.jobs import PermanentJobError
from services.ops_date import ops_date_for
from services.volunteers import (
    ALERT_VOLUNTEER_PENDING,
    VolunteerRegistration,
    register_volunteer,
    set_volunteer_status,
)

pytestmark = [pytest.mark.anyio, requires_postgis]

NOW = datetime(2026, 3, 2, 3, 0, tzinfo=UTC)


def registration(user_id: str = "UV1", district_code: str = PAI):
    return VolunteerRegistration(
        line_user_id=user_id,
        display_name="Somsak",
        full_name=f"จิตอาสา {user_id}",
        phone="0812345678",
        district_code=district_code,
    )


async def add_volunteer(
    sessionmaker,
    user_id: str,
    district_code: str = PAI,
    status: VolunteerStatus = VolunteerStatus.APPROVED,
) -> int:
    async with sessionmaker() as session, session.begin():
        result = await register_volunteer(session, registration(user_id, district_code))
        if status != VolunteerStatus.PENDING:
            await set_volunteer_status(session, result.volunteer.id, status, NOW)
        return result.volunteer.id


async def add_incident(
    sessionmaker,
    status: IncidentStatus = IncidentStatus.OPEN,
    district_code: str = PAI,
) -> int:
    incident = Incident(
        location=WKTElement("SRID=4326;POINT(98.44 19.36)", extended=True),
        district_code=district_code,
        status=status,
        description="ควันขึ้นหลังวัด",
        ops_date=ops_date_for(NOW),
        closed_at=NOW if status == IncidentStatus.CLOSED else None,
    )
    async with sessionmaker() as session, session.begin():
        session.add(incident)
        await session.flush()
        return incident.id


async def accept(sessionmaker, user_id: str, incident_id: int):
    async with sessionmaker() as session, session.begin():
        return await accept_incident(session, user_id, incident_id, NOW)


async def scalar(sessionmaker, statement):
    async with sessionmaker() as session:
        return (await session.execute(statement)).scalar_one()


async def alert_types(sessionmaker) -> list[str]:
    async with sessionmaker() as session:
        rows = await session.execute(
            sa.select(AdminAlert.alert_type).order_by(AdminAlert.id)
        )
        return list(rows.scalars())


class FakeLine:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def multicast(self, to, messages, retry_key=None):
        self.calls.append({"to": list(to), "message": messages, "retry_key": retry_key})
        if self.error is not None:
            raise self.error


@pytest.fixture
def fake_line(monkeypatch):
    line = FakeLine()
    monkeypatch.setattr(jobs_common, "get_line_service", lambda: line)
    return line


async def test_register_creates_pending_volunteer_and_alerts(sessionmaker):
    async with sessionmaker() as session, session.begin():
        result = await register_volunteer(session, registration())

    assert result.created is True
    assert result.volunteer.status == VolunteerStatus.PENDING
    assert await alert_types(sessionmaker) == [ALERT_VOLUNTEER_PENDING]
    assert await scalar(sessionmaker, sa.select(LineUser.display_name)) == "Somsak"


async def test_register_twice_returns_existing(sessionmaker):
    first_id = await add_volunteer(sessionmaker, "UV1")

    async with sessionmaker() as session, session.begin():
        result = await register_volunteer(session, registration("UV1"))

    assert result.created is False
    assert result.volunteer.id == first_id
    assert result.volunteer.status == VolunteerStatus.APPROVED


async def test_approve_sets_approved_at(sessionmaker):
    volunteer_id = await add_volunteer(sessionmaker, "UV1")

    approved_at = await scalar(
        sessionmaker, sa.select(Volunteer.approved_at).where(Volunteer.id == volunteer_id)
    )
    assert approved_at == NOW


async def test_accept_creates_assignment_and_moves_incident_in_progress(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)

    result = await accept(sessionmaker, "UV1", incident_id)

    assert result.outcome == AcceptOutcome.ACCEPTED
    assert result.active_volunteer_count == 1
    status = await scalar(
        sessionmaker, sa.select(Incident.status).where(Incident.id == incident_id)
    )
    assert status == IncidentStatus.IN_PROGRESS
    assert (
        await scalar(sessionmaker, sa.select(IncidentEvent.event_type))
        == "volunteer_accepted"
    )


async def test_accept_twice_is_idempotent(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)

    await accept(sessionmaker, "UV1", incident_id)
    second = await accept(sessionmaker, "UV1", incident_id)

    assert second.outcome == AcceptOutcome.ALREADY_ACCEPTED
    assert await scalar(sessionmaker, sa.select(sa.func.count(Assignment.id))) == 1
    assert await scalar(sessionmaker, sa.select(sa.func.count(IncidentEvent.id))) == 1


async def test_many_volunteers_can_accept_same_incident(sessionmaker):
    for i in range(3):
        await add_volunteer(sessionmaker, f"UV{i}")
    incident_id = await add_incident(sessionmaker)

    results = [await accept(sessionmaker, f"UV{i}", incident_id) for i in range(3)]

    assert [r.active_volunteer_count for r in results] == [1, 2, 3]


async def test_concurrent_double_tap_creates_one_assignment(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)

    results = await asyncio.gather(
        *(accept(sessionmaker, "UV1", incident_id) for _ in range(5))
    )

    outcomes = [result.outcome for result in results]
    assert outcomes.count(AcceptOutcome.ACCEPTED) == 1
    assert outcomes.count(AcceptOutcome.ALREADY_ACCEPTED) == 4
    assert await scalar(sessionmaker, sa.select(sa.func.count(Assignment.id))) == 1


async def test_accept_on_closed_incident_is_rejected(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker, IncidentStatus.CLOSED)

    result = await accept(sessionmaker, "UV1", incident_id)

    assert result.outcome == AcceptOutcome.INCIDENT_CLOSED
    assert await scalar(sessionmaker, sa.select(sa.func.count(Assignment.id))) == 0


@pytest.mark.parametrize(
    "status", [VolunteerStatus.PENDING, VolunteerStatus.SUSPENDED]
)
async def test_unapproved_volunteer_cannot_accept(sessionmaker, status):
    await add_volunteer(sessionmaker, "UV1", status=status)
    incident_id = await add_incident(sessionmaker)

    result = await accept(sessionmaker, "UV1", incident_id)

    assert result.outcome == AcceptOutcome.NOT_VOLUNTEER


async def test_stranger_cannot_accept(sessionmaker):
    incident_id = await add_incident(sessionmaker)

    result = await accept(sessionmaker, "U-random", incident_id)

    assert result.outcome == AcceptOutcome.NOT_VOLUNTEER


async def test_unknown_incident(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")

    result = await accept(sessionmaker, "UV1", 999)

    assert result.outcome == AcceptOutcome.INCIDENT_NOT_FOUND


async def test_dispatch_multicasts_only_approved_volunteers_in_district(
    sessionmaker, fake_line
):
    await add_volunteer(sessionmaker, "UV1")
    await add_volunteer(sessionmaker, "UV2")
    await add_volunteer(sessionmaker, "UV-pending", status=VolunteerStatus.PENDING)
    await add_volunteer(sessionmaker, "UV-other", district_code=MAE_TAENG)
    incident_id = await add_incident(sessionmaker)

    await dispatch_job.handle_dispatch_incident({"incident_id": incident_id}, sessionmaker)

    assert len(fake_line.calls) == 1
    assert fake_line.calls[0]["to"] == ["UV1", "UV2"]
    public_id = await scalar(
        sessionmaker, sa.select(Incident.public_id).where(Incident.id == incident_id)
    )
    assert fake_line.calls[0]["retry_key"] == jobs_common.retry_key(
        "dispatch", public_id, "initial", 0
    )
    assert await scalar(sessionmaker, sa.select(IncidentEvent.event_type)) == (
        EVENT_DISPATCHED
    )


async def test_dispatch_with_no_volunteers_alerts_admin(sessionmaker, fake_line):
    incident_id = await add_incident(sessionmaker)

    await dispatch_job.handle_dispatch_incident({"incident_id": incident_id}, sessionmaker)

    assert fake_line.calls == []
    assert await alert_types(sessionmaker) == [ALERT_NO_VOLUNTEERS]


async def test_dispatch_skips_closed_incident(sessionmaker, fake_line):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker, IncidentStatus.CLOSED)

    await dispatch_job.handle_dispatch_incident({"incident_id": incident_id}, sessionmaker)

    assert fake_line.calls == []


async def test_dispatch_line_failure_propagates_for_retry(sessionmaker, monkeypatch):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    line = FakeLine(error=TimeoutError("LINE down"))
    monkeypatch.setattr(jobs_common, "get_line_service", lambda: line)

    with pytest.raises(TimeoutError):
        await dispatch_job.handle_dispatch_incident(
            {"incident_id": incident_id}, sessionmaker
        )

    assert await scalar(sessionmaker, sa.select(sa.func.count(IncidentEvent.id))) == 0


async def test_dispatch_unknown_incident_is_permanent(sessionmaker, fake_line):
    with pytest.raises(PermanentJobError):
        await dispatch_job.handle_dispatch_incident({"incident_id": 999}, sessionmaker)
