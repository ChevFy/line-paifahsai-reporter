import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from conftest import requires_postgis
from jobs.worker import run_one_job
from models import AdminAlert, Job, JobStatus
from services.jobs import (
    ALERT_JOB_FAILED,
    STALE_RUNNING_TIMEOUT,
    PermanentJobError,
    claim_next_job,
    enqueue_job,
    requeue_stale_jobs,
)

pytestmark = [pytest.mark.anyio, requires_postgis]

NOW = datetime(2026, 3, 2, 3, 0, tzinfo=UTC)


async def enqueue(sessionmaker, key: str = "k1", run_at: datetime | None = None):
    async with sessionmaker() as session, session.begin():
        return await enqueue_job(session, "test_job", {"n": 1}, key, run_at=run_at)


async def get_job(sessionmaker, key: str = "k1") -> Job:
    async with sessionmaker() as session:
        statement = sa.select(Job).where(Job.idempotency_key == key)
        return (await session.execute(statement)).scalar_one()


async def alert_types(sessionmaker) -> list[str]:
    async with sessionmaker() as session:
        rows = await session.execute(sa.select(AdminAlert.alert_type))
        return list(rows.scalars())


async def test_enqueue_is_idempotent(sessionmaker):
    assert await enqueue(sessionmaker) is True
    assert await enqueue(sessionmaker) is False

    async with sessionmaker() as session:
        count = (await session.execute(sa.select(sa.func.count(Job.id)))).scalar_one()
    assert count == 1


async def test_claim_skips_future_jobs(sessionmaker):
    await enqueue(sessionmaker, run_at=NOW + timedelta(minutes=1))

    async with sessionmaker() as session, session.begin():
        assert await claim_next_job(session, "w1", NOW) is None


async def test_concurrent_workers_never_claim_same_job(sessionmaker):
    for i in range(3):
        await enqueue(sessionmaker, key=f"k{i}", run_at=NOW)

    async def claim(worker_id: str):
        async with sessionmaker() as session, session.begin():
            job = await claim_next_job(session, worker_id, NOW)
            await asyncio.sleep(0.05)
            return job.id if job else None

    claimed = await asyncio.gather(*(claim(f"w{i}") for i in range(5)))
    job_ids = [job_id for job_id in claimed if job_id is not None]
    assert sorted(job_ids) == [1, 2, 3]


async def test_successful_job_is_marked_succeeded(sessionmaker):
    await enqueue(sessionmaker, run_at=NOW)
    calls = []

    async def handler(payload, sm):
        calls.append(payload)

    assert await run_one_job(sessionmaker, "w1", {"test_job": handler}) is True

    job = await get_job(sessionmaker)
    assert job.status == JobStatus.SUCCEEDED
    assert job.attempts == 1
    assert calls == [{"n": 1}]


async def test_failed_job_is_retried_later(sessionmaker):
    await enqueue(sessionmaker, run_at=NOW)

    async def handler(payload, sm):
        raise TimeoutError("LINE timeout")

    await run_one_job(sessionmaker, "w1", {"test_job": handler})

    job = await get_job(sessionmaker)
    assert job.status == JobStatus.PENDING
    assert job.run_at > datetime.now(UTC)
    assert "LINE timeout" in job.last_error
    assert await alert_types(sessionmaker) == []


async def test_job_failing_max_attempts_alerts_admin(sessionmaker):
    await enqueue(sessionmaker, run_at=NOW)
    async with sessionmaker() as session, session.begin():
        await session.execute(sa.update(Job).values(attempts=4, max_attempts=5))

    async def handler(payload, sm):
        raise TimeoutError("LINE timeout")

    await run_one_job(sessionmaker, "w1", {"test_job": handler})

    job = await get_job(sessionmaker)
    assert job.status == JobStatus.FAILED
    assert await alert_types(sessionmaker) == [ALERT_JOB_FAILED]


async def test_permanent_error_fails_without_retry(sessionmaker):
    await enqueue(sessionmaker, run_at=NOW)

    async def handler(payload, sm):
        raise PermanentJobError("bad payload")

    await run_one_job(sessionmaker, "w1", {"test_job": handler})

    job = await get_job(sessionmaker)
    assert job.status == JobStatus.FAILED
    assert job.attempts == 1
    assert await alert_types(sessionmaker) == [ALERT_JOB_FAILED]


async def test_unknown_job_type_fails_and_alerts(sessionmaker):
    await enqueue(sessionmaker, run_at=NOW)

    await run_one_job(sessionmaker, "w1", {})

    assert (await get_job(sessionmaker)).status == JobStatus.FAILED
    assert await alert_types(sessionmaker) == [ALERT_JOB_FAILED]


async def test_stale_running_job_is_requeued(sessionmaker):
    await enqueue(sessionmaker, run_at=NOW)
    async with sessionmaker() as session, session.begin():
        await claim_next_job(session, "dead-worker", NOW)

    later = NOW + STALE_RUNNING_TIMEOUT + timedelta(seconds=1)
    async with sessionmaker() as session, session.begin():
        assert await requeue_stale_jobs(session, later) == 1

    job = await get_job(sessionmaker)
    assert job.status == JobStatus.PENDING
    assert job.locked_by is None


async def enqueue_typed(sessionmaker, job_type: str, key: str):
    async with sessionmaker() as session, session.begin():
        await enqueue_job(session, job_type, {}, key, run_at=NOW - timedelta(minutes=1))


async def test_lanes_claim_only_their_job_types(sessionmaker):
    await enqueue_typed(sessionmaker, "dispatch_incident", "big-dispatch")
    await enqueue_typed(sessionmaker, "line_event", "postback")

    async with sessionmaker() as session, session.begin():
        events = await claim_next_job(session, "w", NOW, include_types=["line_event"])
    async with sessionmaker() as session, session.begin():
        background = await claim_next_job(
            session, "w", NOW, exclude_types=["line_event"]
        )
    async with sessionmaker() as session, session.begin():
        nothing_left = await claim_next_job(
            session, "w", NOW, include_types=["line_event"]
        )

    assert events.job_type == "line_event"
    assert background.job_type == "dispatch_incident"
    assert nothing_left is None
