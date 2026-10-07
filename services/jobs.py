import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import AlertSeverity, Job, JobStatus
from services.admin_alerts import record_admin_alert

logger = logging.getLogger(__name__)

RETRY_BASE_DELAY = timedelta(seconds=10)
RETRY_MAX_DELAY = timedelta(minutes=5)
STALE_RUNNING_TIMEOUT = timedelta(minutes=5)
MAX_ERROR_LENGTH = 1000
ALERT_JOB_FAILED = "job_failed"


class PermanentJobError(Exception):
    pass


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    job_type: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


async def enqueue_job(
    session: AsyncSession,
    job_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    run_at: datetime | None = None,
) -> bool:
    values: dict[str, Any] = {
        "job_type": job_type,
        "payload": payload,
        "idempotency_key": idempotency_key,
    }
    if run_at is not None:
        values["run_at"] = run_at
    statement = (
        insert(Job)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[Job.idempotency_key])
        .returning(Job.id)
    )
    job_id = (await session.execute(statement)).scalar_one_or_none()
    if job_id is None:
        logger.info("job already enqueued: idempotency_key=%s", idempotency_key)
        return False
    logger.info(
        "job enqueued: id=%s job_type=%s idempotency_key=%s",
        job_id,
        job_type,
        idempotency_key,
    )
    return True


async def claim_next_job(
    session: AsyncSession,
    worker_id: str,
    now: datetime,
) -> ClaimedJob | None:
    candidate = (
        sa.select(Job.id)
        .where(Job.status == JobStatus.PENDING, Job.run_at <= now)
        .order_by(Job.run_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    statement = (
        sa.update(Job)
        .where(Job.id == candidate)
        .values(
            status=JobStatus.RUNNING,
            attempts=Job.attempts + 1,
            locked_at=now,
            locked_by=worker_id,
        )
        .returning(Job.id, Job.job_type, Job.payload, Job.attempts, Job.max_attempts)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    return ClaimedJob(**row._mapping)


async def complete_job(session: AsyncSession, job: ClaimedJob, now: datetime) -> None:
    await session.execute(
        sa.update(Job)
        .where(Job.id == job.id)
        .values(status=JobStatus.SUCCEEDED, finished_at=now, last_error=None)
    )
    logger.info(
        "job succeeded: id=%s job_type=%s attempts=%s",
        job.id,
        job.job_type,
        job.attempts,
    )


async def fail_job(
    session: AsyncSession,
    job: ClaimedJob,
    error: str,
    now: datetime,
    retryable: bool = True,
) -> None:
    error = error[:MAX_ERROR_LENGTH]
    if retryable and job.attempts < job.max_attempts:
        delay = min(RETRY_BASE_DELAY * 2 ** (job.attempts - 1), RETRY_MAX_DELAY)
        await session.execute(
            sa.update(Job)
            .where(Job.id == job.id)
            .values(
                status=JobStatus.PENDING,
                run_at=now + delay,
                last_error=error,
                locked_at=None,
                locked_by=None,
            )
        )
        logger.warning(
            "job failed, retry %s/%s in %s: id=%s job_type=%s error=%s",
            job.attempts,
            job.max_attempts,
            delay,
            job.id,
            job.job_type,
            error,
        )
        return

    await session.execute(
        sa.update(Job)
        .where(Job.id == job.id)
        .values(status=JobStatus.FAILED, finished_at=now, last_error=error)
    )
    logger.error(
        "job failed permanently: id=%s job_type=%s attempts=%s error=%s",
        job.id,
        job.job_type,
        job.attempts,
        error,
    )
    await record_admin_alert(
        session,
        alert_type=ALERT_JOB_FAILED,
        severity=AlertSeverity.CRITICAL,
        message=(
            f"งาน {job.job_type} (job #{job.id}) ล้มเหลวถาวรหลังลอง {job.attempts} ครั้ง "
            "ระบบจะไม่ลองใหม่เอง กรุณาตรวจสอบและดำเนินการแทน"
        ),
        payload={
            "job_id": job.id,
            "job_type": job.job_type,
            "job_payload": job.payload,
            "error": error,
        },
        dedup_key=f"{ALERT_JOB_FAILED}:{job.id}",
    )


async def requeue_stale_jobs(session: AsyncSession, now: datetime) -> int:
    statement = (
        sa.select(Job)
        .where(
            Job.status == JobStatus.RUNNING,
            Job.locked_at < now - STALE_RUNNING_TIMEOUT,
        )
        .with_for_update(skip_locked=True)
    )
    stale_jobs = (await session.execute(statement)).scalars().all()
    for stale in stale_jobs:
        logger.warning(
            "stale running job: id=%s job_type=%s locked_by=%s attempts=%s",
            stale.id,
            stale.job_type,
            stale.locked_by,
            stale.attempts,
        )
        await fail_job(
            session,
            ClaimedJob(
                id=stale.id,
                job_type=stale.job_type,
                payload=stale.payload,
                attempts=stale.attempts,
                max_attempts=stale.max_attempts,
            ),
            "worker stopped while running (lock timeout)",
            now,
        )
    return len(stale_jobs)
