import asyncio
import base64
import hashlib
import hmac
import json
import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from conftest import MAE_TAENG, TEST_ENV, requires_postgis
from fastapi.testclient import TestClient
from geoalchemy2 import WKTElement
from test_volunteer_flow import (
    NOW,
    FakeLine,
    accept,
    add_incident,
    add_volunteer,
    alert_types,
    scalar,
)

from jobs import common as jobs_common
from jobs import line_events
from jobs.notify import handle_assignment_summary, handle_incident_closed
from line import line_webhook
from models import (
    AssignmentStatus,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Job,
    LineUser,
    Report,
    VolunteerStatus,
)
from services.assignments import (
    ALERT_ALL_WITHDRAWN,
    EVENT_INCIDENT_CLOSED,
    JOB_ASSIGNMENT_SUMMARY,
    JOB_INCIDENT_CLOSED,
    SUMMARY_WINDOW,
    AssignmentAction,
    UpdateOutcome,
    accept_incident,
    summary_window_of,
    update_assignment,
)
from services.dispatch import (
    ESCALATION_DELAY,
    JOB_DISPATCH_INCIDENT,
    JOB_ESCALATE_INCIDENT,
)
from services.escalation import (
    ALERT_INCIDENT_UNACCEPTED,
    EscalationOutcome,
    escalate_if_unaccepted,
)
from services.notifications import load_assignment_summary
from services.ops_date import ops_date_for
from services.volunteers import set_volunteer_status

pytestmark = [pytest.mark.anyio, requires_postgis]

ARRIVED = AssignmentAction.ARRIVED
DONE = AssignmentAction.DONE
WITHDRAW = AssignmentAction.WITHDRAW


async def update(sessionmaker, user_id: str, incident_id: int, action, now=NOW):
    async with sessionmaker() as session, session.begin():
        return await update_assignment(session, user_id, incident_id, action, now)


async def incident_status(sessionmaker, incident_id: int) -> IncidentStatus:
    return await scalar(
        sessionmaker, sa.select(Incident.status).where(Incident.id == incident_id)
    )


async def jobs_of(sessionmaker, job_type: str) -> list[Job]:
    async with sessionmaker() as session:
        rows = await session.execute(
            sa.select(Job).where(Job.job_type == job_type).order_by(Job.id)
        )
        return list(rows.scalars())


@pytest.fixture
def fake_line(monkeypatch):
    line = FakeLine()
    monkeypatch.setattr(jobs_common, "get_line_service", lambda: line)
    return line


async def test_single_volunteer_arrive_then_done_closes_incident(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)

    arrived = await update(sessionmaker, "UV1", incident_id, ARRIVED)
    done = await update(sessionmaker, "UV1", incident_id, DONE)

    assert arrived.outcome == UpdateOutcome.UPDATED
    assert done.outcome == UpdateOutcome.UPDATED
    assert done.incident_closed is True
    assert await incident_status(sessionmaker, incident_id) == IncidentStatus.CLOSED
    closed_jobs = await jobs_of(sessionmaker, JOB_INCIDENT_CLOSED)
    assert [job.payload["incident_id"] for job in closed_jobs] == [incident_id]


async def test_first_done_closes_incident_even_with_others_on_site(sessionmaker):
    first_id = await add_volunteer(sessionmaker, "UV1")
    await add_volunteer(sessionmaker, "UV2")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await accept(sessionmaker, "UV2", incident_id)

    first = await update(sessionmaker, "UV1", incident_id, DONE)

    assert first.incident_closed is True
    assert first.active_volunteer_count == 1
    assert await incident_status(sessionmaker, incident_id) == IncidentStatus.CLOSED

    async with sessionmaker() as session:
        event = (
            await session.execute(
                sa.select(IncidentEvent).where(
                    IncidentEvent.incident_id == incident_id,
                    IncidentEvent.event_type == EVENT_INCIDENT_CLOSED,
                )
            )
        ).scalar_one()
    assert event.payload["volunteer_id"] == first_id
    assert event.payload["others_on_site"] == 1

    closed_jobs = await jobs_of(sessionmaker, JOB_INCIDENT_CLOSED)
    assert [job.payload["closed_by_volunteer_id"] for job in closed_jobs] == [first_id]


async def test_other_volunteer_done_after_close_is_told_closed(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    await add_volunteer(sessionmaker, "UV2")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await accept(sessionmaker, "UV2", incident_id)
    await update(sessionmaker, "UV1", incident_id, DONE)

    second = await update(sessionmaker, "UV2", incident_id, DONE)

    assert second.outcome == UpdateOutcome.INCIDENT_CLOSED
    assert len(await jobs_of(sessionmaker, JOB_INCIDENT_CLOSED)) == 1


async def test_concurrent_done_closes_once(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    await add_volunteer(sessionmaker, "UV2")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await accept(sessionmaker, "UV2", incident_id)

    results = await asyncio.gather(
        update(sessionmaker, "UV1", incident_id, DONE),
        update(sessionmaker, "UV2", incident_id, DONE),
    )

    outcomes = sorted(result.outcome for result in results)
    assert outcomes == sorted([UpdateOutcome.UPDATED, UpdateOutcome.INCIDENT_CLOSED])
    assert len(await jobs_of(sessionmaker, JOB_INCIDENT_CLOSED)) == 1


async def test_everyone_withdraws_reopens_redispatches_and_alerts(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)

    result = await update(sessionmaker, "UV1", incident_id, WITHDRAW)

    assert result.all_withdrawn is True
    assert await incident_status(sessionmaker, incident_id) == IncidentStatus.OPEN
    assert ALERT_ALL_WITHDRAWN in await alert_types(sessionmaker)
    dispatches = await jobs_of(sessionmaker, JOB_DISPATCH_INCIDENT)
    assert [job.payload["reason"] for job in dispatches] == ["all_withdrawn"]


async def test_withdraw_then_rejoin_then_withdraw_again_redispatches_again(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)

    for _ in range(2):
        await accept(sessionmaker, "UV1", incident_id)
        await update(sessionmaker, "UV1", incident_id, WITHDRAW)

    dispatches = await jobs_of(sessionmaker, JOB_DISPATCH_INCIDENT)
    assert len(dispatches) == 2
    assert len({job.payload["round"] for job in dispatches}) == 2


async def test_withdraw_with_others_left_enqueues_summary_only(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    await add_volunteer(sessionmaker, "UV2")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await accept(sessionmaker, "UV2", incident_id)

    result = await update(
        sessionmaker, "UV1", incident_id, WITHDRAW, now=NOW + timedelta(minutes=10)
    )

    assert result.active_volunteer_count == 1
    assert result.all_withdrawn is False
    assert len(await jobs_of(sessionmaker, JOB_ASSIGNMENT_SUMMARY)) == 2
    assert await jobs_of(sessionmaker, JOB_DISPATCH_INCIDENT) == []


async def test_accepts_in_same_window_are_batched_into_one_summary(sessionmaker):
    for i in range(3):
        await add_volunteer(sessionmaker, f"UV{i}")
    incident_id = await add_incident(sessionmaker)

    for i in range(3):
        await accept(sessionmaker, f"UV{i}", incident_id)

    summaries = await jobs_of(sessionmaker, JOB_ASSIGNMENT_SUMMARY)
    assert len(summaries) == 1
    assert summaries[0].run_at > NOW


async def test_done_twice_is_told_closed(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)

    await update(sessionmaker, "UV1", incident_id, DONE)
    again = await update(sessionmaker, "UV1", incident_id, DONE)

    assert again.outcome == UpdateOutcome.INCIDENT_CLOSED
    assert len(await jobs_of(sessionmaker, JOB_INCIDENT_CLOSED)) == 1


async def test_arrived_twice_is_unchanged(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await update(sessionmaker, "UV1", incident_id, ARRIVED)

    again = await update(sessionmaker, "UV1", incident_id, ARRIVED)

    assert again.outcome == UpdateOutcome.UNCHANGED
    assert again.assignment_status == AssignmentStatus.ARRIVED


async def test_arrived_after_withdraw_is_invalid(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    await add_volunteer(sessionmaker, "UV2")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await accept(sessionmaker, "UV2", incident_id)
    await update(sessionmaker, "UV1", incident_id, WITHDRAW)

    result = await update(sessionmaker, "UV1", incident_id, ARRIVED)

    assert result.outcome == UpdateOutcome.INVALID_TRANSITION


async def test_update_without_assignment(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)

    result = await update(sessionmaker, "UV1", incident_id, DONE)

    assert result.outcome == UpdateOutcome.NOT_ASSIGNED


async def test_old_done_button_after_close(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await update(sessionmaker, "UV1", incident_id, DONE)

    result = await update(sessionmaker, "UV1", incident_id, WITHDRAW)

    assert result.outcome == UpdateOutcome.INCIDENT_CLOSED


async def escalate(sessionmaker, incident_id: int):
    async with sessionmaker() as session, session.begin():
        return await escalate_if_unaccepted(session, incident_id, NOW)


async def test_escalation_without_volunteers_redispatches_and_alerts(sessionmaker):
    incident_id = await add_incident(sessionmaker)

    outcome = await escalate(sessionmaker, incident_id)

    assert outcome == EscalationOutcome.ESCALATED
    assert await alert_types(sessionmaker) == [ALERT_INCIDENT_UNACCEPTED]
    dispatches = await jobs_of(sessionmaker, JOB_DISPATCH_INCIDENT)
    assert [job.payload["reason"] for job in dispatches] == ["escalation"]


async def test_escalation_skipped_when_someone_accepted(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)

    assert await escalate(sessionmaker, incident_id) == EscalationOutcome.HAS_VOLUNTEERS
    assert await jobs_of(sessionmaker, JOB_DISPATCH_INCIDENT) == []


async def test_escalation_skipped_for_closed_incident(sessionmaker):
    incident_id = await add_incident(sessionmaker, IncidentStatus.CLOSED)

    assert await escalate(sessionmaker, incident_id) == EscalationOutcome.INACTIVE


async def test_summary_job_multicasts_names_to_district(sessionmaker, fake_line):
    await add_volunteer(sessionmaker, "UV1")
    await add_volunteer(sessionmaker, "UV2")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)

    await handle_assignment_summary(
        {"incident_id": incident_id, "window": summary_window_of(NOW)}, sessionmaker
    )

    assert len(fake_line.calls) == 1
    assert fake_line.calls[0]["to"] == ["UV1", "UV2"]
    text = fake_line.calls[0]["message"].text
    assert "➕ ขอไป: จิตอาสา" in text
    assert "1 คน" in text


async def test_summary_names_who_joined_and_withdrew_in_window(
    sessionmaker, fake_line
):
    for user_id in ("UV1", "UV2", "UV3"):
        await add_volunteer(sessionmaker, user_id)
    incident_id = await add_incident(sessionmaker)
    earlier = NOW - SUMMARY_WINDOW
    async with sessionmaker() as session, session.begin():
        await accept_incident(session, "UV1", incident_id, earlier)
    await accept(sessionmaker, "UV2", incident_id)
    await accept(sessionmaker, "UV3", incident_id)
    await update(sessionmaker, "UV3", incident_id, WITHDRAW)

    await handle_assignment_summary(
        {"incident_id": incident_id, "window": summary_window_of(NOW)}, sessionmaker
    )

    lines = fake_line.calls[0]["message"].text.splitlines()
    assert lines[1] == "➕ ขอไป: จิตอาสา, จิตอาสา"
    assert lines[2] == "➖ ถอนตัว: จิตอาสา"
    assert lines[3] == "ตอนนี้มีจิตอาสารับงาน 2 คน: จิตอาสา, จิตอาสา"


async def test_summary_window_excludes_other_windows(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    async with sessionmaker() as session, session.begin():
        await accept_incident(session, "UV1", incident_id, NOW - SUMMARY_WINDOW)

    async with sessionmaker() as session:
        summary = await load_assignment_summary(
            session, incident_id, summary_window_of(NOW)
        )

    assert summary.joined_names == []
    assert len(summary.volunteer_names) == 1


async def test_summary_job_skips_closed_incident(sessionmaker, fake_line):
    incident_id = await add_incident(sessionmaker, IncidentStatus.CLOSED)

    await handle_assignment_summary(
        {"incident_id": incident_id, "window": 1}, sessionmaker
    )

    assert fake_line.calls == []


async def test_closure_job_notifies_reporters_and_volunteers(sessionmaker, fake_line):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    async with sessionmaker() as session, session.begin():
        for user_id in ("UR1", "UR2", "UR1"):
            await session.merge(LineUser(user_id=user_id))
            session.add(
                Report(
                    incident_id=incident_id,
                    reporter_user_id=user_id,
                    location=WKTElement("SRID=4326;POINT(98.44 19.36)", extended=True),
                    ops_date=ops_date_for(NOW),
                    client_request_id=uuid.uuid4(),
                )
            )
    await add_volunteer(sessionmaker, "UV2")
    await add_volunteer(sessionmaker, "UV3", district_code=MAE_TAENG)
    await accept(sessionmaker, "UV1", incident_id)
    await update(sessionmaker, "UV1", incident_id, DONE)
    job = (await jobs_of(sessionmaker, JOB_INCIDENT_CLOSED))[0]

    await handle_incident_closed(job.payload, sessionmaker)

    reporter_call, volunteer_call = fake_line.calls
    assert reporter_call["to"] == ["UR1", "UR2"]
    assert "1362" in reporter_call["message"].text
    assert volunteer_call["to"] == ["UV1", "UV2"]
    assert "จิตอาสา กด \"เรียบร้อยแล้ว\"" in volunteer_call["message"].text
    assert "1362" in volunteer_call["message"].text
    assert reporter_call["retry_key"] != volunteer_call["retry_key"]


def signed_request(body: dict) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    digest = hmac.new(TEST_ENV["LINE_CHANNEL_SECRET"].encode(), raw, hashlib.sha256)
    signature = base64.b64encode(digest.digest()).decode()
    return raw, {"X-Line-Signature": signature, "Content-Type": "application/json"}


def postback_raw(event_id: str) -> dict:
    return {
        "type": "postback",
        "mode": "active",
        "timestamp": 0,
        "webhookEventId": event_id,
        "deliveryContext": {"isRedelivery": False},
        "replyToken": "reply-token",
        "source": {"type": "user", "userId": "UV1"},
        "postback": {"data": "action=accept&incident_id=1"},
    }


async def test_webhook_persists_events_and_dedups_redelivery(sessionmaker, monkeypatch):
    from api.utils_api import app

    monkeypatch.setattr(line_webhook, "SessionLocal", sessionmaker)
    client = TestClient(app)
    raw, headers = signed_request(
        {"destination": "x", "events": [postback_raw("E1"), postback_raw("E2")]}
    )

    first = client.post("/webhook", content=raw, headers=headers)
    redelivered = client.post("/webhook", content=raw, headers=headers)

    assert first.status_code == 200
    assert redelivered.status_code == 200
    keys = [job.idempotency_key for job in await jobs_of(sessionmaker, "line_event")]
    assert keys == ["line_event:E1", "line_event:E2"]


async def test_webhook_rejects_bad_signature(sessionmaker, monkeypatch):
    from api.utils_api import app

    monkeypatch.setattr(line_webhook, "SessionLocal", sessionmaker)
    raw, headers = signed_request({"events": [postback_raw("E1")]})

    response = TestClient(app).post(
        "/webhook", content=raw, headers=headers | {"X-Line-Signature": "forged"}
    )

    assert response.status_code == 400
    assert await jobs_of(sessionmaker, "line_event") == []


async def test_line_event_job_dispatches_to_handler(sessionmaker, monkeypatch):
    handled = []

    async def fake_handle(event):
        handled.append(event)

    monkeypatch.setattr(line_events, "handle_event", fake_handle)

    await line_events.handle_line_event({"event": postback_raw("E1")}, sessionmaker)
    await line_events.handle_line_event(
        {"event": {"type": "brandNewType", "webhookEventId": "E2"}}, sessionmaker
    )

    assert [type(event).__name__ for event in handled] == ["PostbackEvent"]



async def test_suspended_volunteer_cannot_mark_done(sessionmaker):
    volunteer_id = await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    async with sessionmaker() as session, session.begin():
        await set_volunteer_status(
            session, volunteer_id, VolunteerStatus.SUSPENDED, NOW
        )

    done = await update(sessionmaker, "UV1", incident_id, DONE)
    arrived = await update(sessionmaker, "UV1", incident_id, ARRIVED)

    assert done.outcome == UpdateOutcome.VOLUNTEER_NOT_APPROVED
    assert arrived.outcome == UpdateOutcome.VOLUNTEER_NOT_APPROVED
    assert await incident_status(sessionmaker, incident_id) == IncidentStatus.IN_PROGRESS


async def test_suspended_volunteer_can_still_withdraw(sessionmaker):
    volunteer_id = await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    async with sessionmaker() as session, session.begin():
        await set_volunteer_status(
            session, volunteer_id, VolunteerStatus.SUSPENDED, NOW
        )

    result = await update(sessionmaker, "UV1", incident_id, WITHDRAW)

    assert result.outcome == UpdateOutcome.UPDATED
    assert result.all_withdrawn is True


async def test_all_withdrawn_schedules_new_escalation_round(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)

    await update(sessionmaker, "UV1", incident_id, WITHDRAW)

    checks = await jobs_of(sessionmaker, JOB_ESCALATE_INCIDENT)
    assert len(checks) == 1
    assert checks[0].payload["round"].startswith("all_withdrawn:")
    assert checks[0].payload["after_event_id"] > 0
    assert checks[0].run_at == NOW + ESCALATION_DELAY


async def escalate_round(sessionmaker, incident_id: int, round_key: str, after: int):
    async with sessionmaker() as session, session.begin():
        return await escalate_if_unaccepted(
            session, incident_id, NOW, round_key=round_key, after_event_id=after
        )


async def test_initial_escalation_superseded_by_all_withdrawn_round(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await update(sessionmaker, "UV1", incident_id, WITHDRAW)
    dispatches_before = len(await jobs_of(sessionmaker, JOB_DISPATCH_INCIDENT))

    outcome = await escalate(sessionmaker, incident_id)

    assert outcome == EscalationOutcome.SUPERSEDED
    assert len(await jobs_of(sessionmaker, JOB_DISPATCH_INCIDENT)) == dispatches_before


async def test_each_round_escalates_once(sessionmaker):
    await add_volunteer(sessionmaker, "UV1")
    incident_id = await add_incident(sessionmaker)
    await accept(sessionmaker, "UV1", incident_id)
    await update(sessionmaker, "UV1", incident_id, WITHDRAW)
    check = (await jobs_of(sessionmaker, JOB_ESCALATE_INCIDENT))[0]
    round_key = check.payload["round"]
    after = check.payload["after_event_id"]

    first = await escalate_round(sessionmaker, incident_id, round_key, after)
    second = await escalate_round(sessionmaker, incident_id, round_key, after)

    assert first == second == EscalationOutcome.ESCALATED
    escalations = [
        job
        for job in await jobs_of(sessionmaker, JOB_DISPATCH_INCIDENT)
        if job.payload["reason"] == "escalation"
    ]
    assert [job.payload["round"] for job in escalations] == [f"escalation:{round_key}"]
