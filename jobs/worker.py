import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.dispatch import handle_dispatch_incident
from jobs.escalation import handle_escalate_incident
from jobs.line_events import JOB_LINE_EVENT, handle_line_event
from jobs.notify import handle_assignment_summary, handle_incident_closed
from services.assignments import JOB_ASSIGNMENT_SUMMARY, JOB_INCIDENT_CLOSED
from services.dispatch import JOB_DISPATCH_INCIDENT, JOB_ESCALATE_INCIDENT
from services.jobs import (
    PermanentJobError,
    claim_next_job,
    complete_job,
    fail_job,
    requeue_stale_jobs,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 2.0
STALE_CHECK_INTERVAL = timedelta(minutes=1)

JobHandler = Callable[[dict[str, Any], async_sessionmaker], Awaitable[None]]

HANDLERS: dict[str, JobHandler] = {
    JOB_LINE_EVENT: handle_line_event,
    JOB_DISPATCH_INCIDENT: handle_dispatch_incident,
    JOB_ESCALATE_INCIDENT: handle_escalate_incident,
    JOB_ASSIGNMENT_SUMMARY: handle_assignment_summary,
    JOB_INCIDENT_CLOSED: handle_incident_closed,
}



@dataclass(frozen=True)
class WorkerLane:
    name: str
    include_types: Collection[str] | None = None
    exclude_types: Collection[str] | None = None


EVENTS_LANE = WorkerLane("events", include_types=(JOB_LINE_EVENT,))
BACKGROUND_LANE = WorkerLane("background", exclude_types=(JOB_LINE_EVENT,))
ALL_LANE = WorkerLane("all")
LANES = (EVENTS_LANE, BACKGROUND_LANE)

_wake_events: set[asyncio.Event] = set()


def wake_worker() -> None:
    for event in _wake_events:
        event.set()


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def run_one_job(
    sessionmaker: async_sessionmaker,
    worker_id: str,
    handlers: dict[str, JobHandler] = HANDLERS,
    lane: WorkerLane = ALL_LANE,
) -> bool:
    async with sessionmaker() as session, session.begin():
        job = await claim_next_job(
            session,
            worker_id,
            datetime.now(UTC),
            include_types=lane.include_types,
            exclude_types=lane.exclude_types,
        )
    if job is None:
        return False

    logger.info(
        "job started: id=%s job_type=%s attempt=%s/%s",
        job.id,
        job.job_type,
        job.attempts,
        job.max_attempts,
    )
    try:
        handler = handlers.get(job.job_type)
        if handler is None:
            raise PermanentJobError(f"no handler for job_type={job.job_type}")
        await handler(job.payload, sessionmaker)
    except Exception as error:
        logger.exception("job raised: id=%s job_type=%s", job.id, job.job_type)
        async with sessionmaker() as session, session.begin():
            await fail_job(
                session,
                job,
                f"{type(error).__name__}: {error}",
                datetime.now(UTC),
                retryable=not isinstance(error, PermanentJobError),
            )
        return True

    async with sessionmaker() as session, session.begin():
        await complete_job(session, job, datetime.now(UTC))
    return True


async def run_worker(
    sessionmaker: async_sessionmaker,
    stop: asyncio.Event,
    lane: WorkerLane = ALL_LANE,
    worker_id: str | None = None,
) -> None:
    worker_id = f"{worker_id or default_worker_id()}:{lane.name}"
    wake = asyncio.Event()
    _wake_events.add(wake)
    logger.info("job worker started: worker_id=%s", worker_id)
    next_stale_check = datetime.now(UTC)

    try:
        while not stop.is_set():
            processed = False
            try:
                now = datetime.now(UTC)
                if now >= next_stale_check:
                    async with sessionmaker() as session, session.begin():
                        await requeue_stale_jobs(session, now)
                    next_stale_check = now + STALE_CHECK_INTERVAL
                processed = await run_one_job(sessionmaker, worker_id, lane=lane)
            except Exception:
                logger.exception("job worker loop error: worker_id=%s", worker_id)

            if not processed:
                try:
                    await asyncio.wait_for(wake.wait(), POLL_INTERVAL_SECONDS)
                except TimeoutError:
                    pass
                wake.clear()
    finally:
        _wake_events.discard(wake)
    logger.info("job worker stopped: worker_id=%s", worker_id)


def log_worker_exit(task: asyncio.Task) -> None:
    if task.cancelled():
        logger.warning("job worker task cancelled")
        return
    error = task.exception()
    if error is not None:
        logger.critical("job worker crashed, no jobs will run", exc_info=error)
