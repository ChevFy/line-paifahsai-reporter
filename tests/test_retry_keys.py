import pytest
import sqlalchemy as sa
from conftest import requires_postgis
from test_volunteer_flow import NOW, FakeLine, accept, add_incident, add_volunteer

from jobs import common as jobs_common
from jobs import dispatch as dispatch_job
from jobs.notify import handle_assignment_summary, handle_incident_closed
from models import Incident
from services.assignments import summary_window_of

pytestmark = [pytest.mark.anyio, requires_postgis]


@pytest.fixture
def fake_line(monkeypatch):
    line = FakeLine()
    monkeypatch.setattr(jobs_common, "get_line_service", lambda: line)
    return line


async def reset_incident_ids(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        await session.execute(
            sa.text(
                "TRUNCATE incidents, incident_events, assignments, jobs "
                "RESTART IDENTITY CASCADE"
            )
        )


async def send_everything(sessionmaker, incident_id: int) -> None:
    await dispatch_job.handle_dispatch_incident(
        {"incident_id": incident_id, "reason": "initial", "round": "initial"},
        sessionmaker,
    )
    await accept(sessionmaker, "UV1", incident_id)
    await handle_assignment_summary(
        {"incident_id": incident_id, "window": summary_window_of(NOW)}, sessionmaker
    )
    await handle_incident_closed(
        {"incident_id": incident_id, "closed_at": NOW.isoformat()}, sessionmaker
    )


async def test_reused_incident_id_gets_fresh_retry_keys(sessionmaker, fake_line):
    await add_volunteer(sessionmaker, "UV1")
    first_id = await add_incident(sessionmaker)
    await send_everything(sessionmaker, first_id)
    first_keys = [call["retry_key"] for call in fake_line.calls]

    await reset_incident_ids(sessionmaker)
    fake_line.calls.clear()
    second_id = await add_incident(sessionmaker)
    await send_everything(sessionmaker, second_id)
    second_keys = [call["retry_key"] for call in fake_line.calls]

    assert second_id == first_id
    assert len(first_keys) == len(second_keys) == 3
    assert set(first_keys).isdisjoint(second_keys)


async def test_public_id_is_generated_and_unique(sessionmaker):
    ids = [await add_incident(sessionmaker) for _ in range(3)]

    async with sessionmaker() as session:
        public_ids = (
            await session.execute(
                sa.select(Incident.public_id).where(Incident.id.in_(ids))
            )
        ).scalars().all()

    assert len(set(public_ids)) == 3
    assert all(public_id is not None for public_id in public_ids)
