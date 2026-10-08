from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from conftest import MAE_TAENG, PAI, requires_postgis

from jobs import common as jobs_common
from jobs.volunteer_notice import handle_volunteer_status_notice
from models import AdminAlert, Job, VolunteerStatus
from services.jobs import PermanentJobError
from services.volunteers import (
    ALERT_VOLUNTEER_PENDING,
    JOB_VOLUNTEER_STATUS_NOTICE,
    VolunteerRegistration,
    count_volunteers,
    list_volunteers,
    register_volunteer,
    set_volunteer_status,
)

pytestmark = [pytest.mark.anyio, requires_postgis]

NOW = datetime(2026, 3, 2, 3, 0, tzinfo=UTC)


class FakeLine:
    def __init__(self, error: Exception | None = None):
        self.pushes = []
        self.error = error

    async def push(self, to, messages, retry_key=None):
        self.pushes.append({"to": to, "message": messages, "retry_key": retry_key})
        if self.error is not None:
            raise self.error


@pytest.fixture
def fake_line(monkeypatch):
    line = FakeLine()
    monkeypatch.setattr(jobs_common, "get_line_service", lambda: line)
    return line


async def register(sessionmaker, user_id: str, district_code: str = PAI) -> int:
    async with sessionmaker() as session, session.begin():
        result = await register_volunteer(
            session,
            VolunteerRegistration(
                line_user_id=user_id,
                display_name=None,
                full_name=f"จิตอาสา {user_id}",
                phone="0812345678",
                district_code=district_code,
            ),
        )
        return result.volunteer.id


async def change(sessionmaker, volunteer_id: int, status, now=NOW, actor="admin:ops"):
    async with sessionmaker() as session, session.begin():
        return await set_volunteer_status(session, volunteer_id, status, now, actor)


async def notice_jobs(sessionmaker) -> list[Job]:
    async with sessionmaker() as session:
        statement = (
            sa.select(Job)
            .where(Job.job_type == JOB_VOLUNTEER_STATUS_NOTICE)
            .order_by(Job.id)
        )
        return list((await session.execute(statement)).scalars().all())


async def test_pagination_is_stable_and_counts_filtered_total(sessionmaker):
    ids = [await register(sessionmaker, f"U{n}") for n in range(5)]
    await register(sessionmaker, "UOTHER", MAE_TAENG)

    async with sessionmaker() as session:
        first = await list_volunteers(session, district_code=PAI, limit=2, offset=0)
        second = await list_volunteers(session, district_code=PAI, limit=2, offset=2)
        last = await list_volunteers(session, district_code=PAI, limit=2, offset=4)
        beyond = await list_volunteers(session, district_code=PAI, limit=2, offset=6)
        total = await count_volunteers(session, district_code=PAI)
        everyone = await count_volunteers(session)

    assert [v.id for v in first + second + last] == ids
    assert beyond == []
    assert total == 5
    assert everyone == 6


async def test_count_filters_by_status(sessionmaker):
    first = await register(sessionmaker, "U1")
    await register(sessionmaker, "U2")
    await change(sessionmaker, first, VolunteerStatus.APPROVED)

    async with sessionmaker() as session:
        approved = await count_volunteers(session, status=VolunteerStatus.APPROVED)
        pending = await count_volunteers(session, status=VolunteerStatus.PENDING)

    assert (approved, pending) == (1, 1)


async def test_approve_acknowledges_pending_alert_and_enqueues_notice(sessionmaker):
    volunteer_id = await register(sessionmaker, "U1")

    volunteer = await change(sessionmaker, volunteer_id, VolunteerStatus.APPROVED)

    assert volunteer.status == VolunteerStatus.APPROVED
    assert volunteer.approved_at == NOW
    async with sessionmaker() as session:
        alert = (
            await session.execute(
                sa.select(AdminAlert).where(
                    AdminAlert.dedup_key == f"{ALERT_VOLUNTEER_PENDING}:{volunteer_id}"
                )
            )
        ).scalar_one()
    assert alert.acknowledged_at == NOW
    assert alert.acknowledged_by == "admin:ops"

    jobs = await notice_jobs(sessionmaker)
    assert len(jobs) == 1
    assert jobs[0].payload["volunteer_id"] == volunteer_id
    assert jobs[0].payload["status"] == "approved"


async def test_approve_twice_does_not_notify_twice(sessionmaker):
    volunteer_id = await register(sessionmaker, "U1")

    await change(sessionmaker, volunteer_id, VolunteerStatus.APPROVED)
    await change(
        sessionmaker,
        volunteer_id,
        VolunteerStatus.APPROVED,
        now=NOW + timedelta(minutes=1),
    )

    assert len(await notice_jobs(sessionmaker)) == 1


async def test_reinstate_after_suspend_keeps_first_approved_at(sessionmaker):
    volunteer_id = await register(sessionmaker, "U1")
    await change(sessionmaker, volunteer_id, VolunteerStatus.APPROVED)
    await change(
        sessionmaker, volunteer_id, VolunteerStatus.SUSPENDED, NOW + timedelta(days=1)
    )

    volunteer = await change(
        sessionmaker, volunteer_id, VolunteerStatus.APPROVED, NOW + timedelta(days=2)
    )

    assert volunteer.approved_at == NOW
    statuses = [job.payload["status"] for job in await notice_jobs(sessionmaker)]
    assert statuses == ["approved", "suspended", "approved"]


async def test_notice_job_pushes_to_volunteer(sessionmaker, fake_line):
    volunteer_id = await register(sessionmaker, "U1")
    await change(sessionmaker, volunteer_id, VolunteerStatus.APPROVED)
    job = (await notice_jobs(sessionmaker))[0]

    await handle_volunteer_status_notice(job.payload, sessionmaker)
    await handle_volunteer_status_notice(job.payload, sessionmaker)

    assert [push["to"] for push in fake_line.pushes] == ["U1", "U1"]
    assert "อนุมัติ" in fake_line.pushes[0]["message"].text
    assert "ปาย" in fake_line.pushes[0]["message"].text
    assert fake_line.pushes[0]["retry_key"] == fake_line.pushes[1]["retry_key"]


async def test_superseded_notice_is_skipped(sessionmaker, fake_line):
    volunteer_id = await register(sessionmaker, "U1")
    await change(sessionmaker, volunteer_id, VolunteerStatus.APPROVED)
    await change(
        sessionmaker,
        volunteer_id,
        VolunteerStatus.SUSPENDED,
        now=NOW + timedelta(minutes=1),
    )
    approved_job = (await notice_jobs(sessionmaker))[0]

    await handle_volunteer_status_notice(approved_job.payload, sessionmaker)

    assert fake_line.pushes == []


async def test_notice_job_propagates_line_failure(sessionmaker, monkeypatch):
    line = FakeLine(error=TimeoutError("LINE down"))
    monkeypatch.setattr(jobs_common, "get_line_service", lambda: line)
    volunteer_id = await register(sessionmaker, "U1")
    await change(sessionmaker, volunteer_id, VolunteerStatus.APPROVED)
    job = (await notice_jobs(sessionmaker))[0]

    with pytest.raises(TimeoutError):
        await handle_volunteer_status_notice(job.payload, sessionmaker)


async def test_notice_job_rejects_bad_payload(sessionmaker):
    with pytest.raises(PermanentJobError):
        await handle_volunteer_status_notice({"status": "approved"}, sessionmaker)
    with pytest.raises(PermanentJobError):
        await handle_volunteer_status_notice(
            {"volunteer_id": 999, "status": "approved"}, sessionmaker
        )
