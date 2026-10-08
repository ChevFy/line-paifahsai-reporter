from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from linebot.v3.webhooks import PostbackEvent

from line import line_handler
from line.line_flex import (
    ACTION_ACCEPT,
    build_incident_alert,
    first_name,
    parse_postback_data,
    postback_data,
)
from models import AssignmentStatus
from services.assignments import (
    AcceptOutcome,
    AcceptResult,
    AssignmentAction,
    UpdateOutcome,
    UpdateResult,
)
from services.dispatch import DispatchReason, DispatchTarget

pytestmark = pytest.mark.anyio



@pytest.fixture
def anyio_backend():
    return "asyncio"


def target(**overrides) -> DispatchTarget:
    values = {
        "incident_id": 42,
        "latitude": 19.36,
        "longitude": 98.44,
        "district_code": "5803",
        "district_name": "ปาย",
        "province_name": "แม่ฮ่องสอน",
        "description": "ควันขึ้นหลังวัด",
        "reason": DispatchReason.INITIAL,
        "created_at": datetime(2026, 3, 2, 3, 0, tzinfo=UTC),
        "recipients": ["UV1"],
    }
    return DispatchTarget(**(values | overrides))


def postback_event(data: str, user_id: str = "UV1") -> PostbackEvent:
    return PostbackEvent.from_dict(
        {
            "type": "postback",
            "mode": "active",
            "timestamp": 0,
            "webhookEventId": "01HZXAMPLEEVENTID",
            "deliveryContext": {"isRedelivery": False},
            "replyToken": "reply-token",
            "source": {"type": "user", "userId": user_id},
            "postback": {"data": data},
        }
    )


def message_text(message) -> str:
    return getattr(message, "text", None) or message.alt_text


class Recorder:
    def __init__(self, reply_error: Exception | None = None):
        self.replies = []
        self.pushes = []
        self.reply_error = reply_error


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()

    async def fake_reply(reply_token, messages):
        if rec.reply_error is not None:
            raise rec.reply_error
        rec.replies.append(message_text(messages))

    async def fake_push(user_id, messages, retry_key=None):
        rec.pushes.append((user_id, message_text(messages), retry_key))

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr(line_handler, "reply_message", fake_reply)
    monkeypatch.setattr(line_handler, "push_message", fake_push)
    monkeypatch.setattr(line_handler, "SessionLocal", fake_session)
    return rec


class FakeSession:
    @asynccontextmanager
    async def begin(self):
        yield


def use_accept(monkeypatch, result: AcceptResult, calls: list | None = None):
    async def fake_accept(session, line_user_id, incident_id, now):
        if calls is not None:
            calls.append((line_user_id, incident_id))
        return result

    monkeypatch.setattr(line_handler, "accept_incident", fake_accept)


def test_postback_data_round_trip():
    data = postback_data(ACTION_ACCEPT, 42)

    assert parse_postback_data(data) == (ACTION_ACCEPT, 42)
    assert len(data) <= 300


@pytest.mark.parametrize(
    "data",
    ["", "action=accept", "action=accept&incident_id=abc", "action=nuke&incident_id=1"],
)
def test_parse_rejects_bad_data(data):
    assert parse_postback_data(data) is None


def test_flex_has_accept_button_and_map():
    message = build_incident_alert(target()).to_dict()
    footer = message["contents"]["footer"]["contents"]

    assert footer[0]["action"]["type"] == "postback"
    assert parse_postback_data(footer[0]["action"]["data"]) == (ACTION_ACCEPT, 42)
    assert "19.360000,98.440000" in footer[1]["action"]["uri"]
    assert len(footer) == 2
    assert "ดูรูป" not in str(message)
    assert "#42" in message["altText"]


def test_flex_without_description():
    message = build_incident_alert(target(description=None)).to_dict()
    texts = [item["text"] for item in message["contents"]["body"]["contents"]]

    assert "ควันขึ้นหลังวัด" not in texts


async def test_accept_postback_replies_with_count(recorder, monkeypatch):
    calls = []
    use_accept(monkeypatch, AcceptResult(AcceptOutcome.ACCEPTED, 42, 3), calls)

    await line_handler.handle_event(postback_event("action=accept&incident_id=42"))

    assert calls == [("UV1", 42)]
    assert len(recorder.replies) == 1
    assert "#42" in recorder.replies[0]
    assert "3 คน" in recorder.replies[0]


async def test_closed_incident_postback_tells_volunteer_not_to_go(recorder, monkeypatch):
    use_accept(monkeypatch, AcceptResult(AcceptOutcome.INCIDENT_CLOSED, 42))

    await line_handler.handle_event(postback_event("action=accept&incident_id=42"))

    assert "ปิดไปแล้ว" in recorder.replies[0]


async def test_garbage_postback_replies_stale_button(recorder, monkeypatch):
    use_accept(monkeypatch, AcceptResult(AcceptOutcome.ACCEPTED, 1, 1))

    await line_handler.handle_event(postback_event("action=nuke"))

    assert recorder.replies == [line_handler.STALE_BUTTON_MESSAGE]


async def test_reply_failure_falls_back_to_push(recorder, monkeypatch):
    recorder.reply_error = TimeoutError("reply token expired")
    use_accept(monkeypatch, AcceptResult(AcceptOutcome.ACCEPTED, 42, 1))

    await line_handler.handle_event(postback_event("action=accept&incident_id=42"))

    assert len(recorder.pushes) == 1
    user_id, text, retry_key = recorder.pushes[0]
    assert user_id == "UV1"
    assert "#42" in text
    assert retry_key is not None


async def test_accept_db_error_propagates_for_job_retry(recorder, monkeypatch):
    async def explode(session, line_user_id, incident_id, now):
        raise RuntimeError("db down")

    monkeypatch.setattr(line_handler, "accept_incident", explode)

    with pytest.raises(RuntimeError, match="db down"):
        await line_handler.handle_event(postback_event("action=accept&incident_id=42"))

    assert recorder.replies == []


def use_update(monkeypatch, result: UpdateResult, calls: list | None = None):
    async def fake_update(session, line_user_id, incident_id, action, now):
        if calls is not None:
            calls.append((line_user_id, incident_id, action))
        return result

    monkeypatch.setattr(line_handler, "update_assignment", fake_update)


async def test_accept_reply_has_status_buttons(monkeypatch):
    sent = []

    async def fake_reply(reply_token, messages):
        sent.append(messages)

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr(line_handler, "reply_message", fake_reply)
    monkeypatch.setattr(line_handler, "SessionLocal", fake_session)
    use_accept(monkeypatch, AcceptResult(AcceptOutcome.ACCEPTED, 42, 1))

    await line_handler.handle_event(postback_event("action=accept&incident_id=42"))

    footer = sent[0].to_dict()["contents"]["footer"]["contents"]
    actions = [parse_postback_data(button["action"]["data"]) for button in footer]
    assert actions == [("arrived", 42), ("done", 42), ("withdraw", 42)]


@pytest.mark.parametrize(
    ("data", "action"),
    [
        ("action=arrived&incident_id=42", AssignmentAction.ARRIVED),
        ("action=done&incident_id=42", AssignmentAction.DONE),
        ("action=withdraw&incident_id=42", AssignmentAction.WITHDRAW),
    ],
)
async def test_status_buttons_route_to_update(recorder, monkeypatch, data, action):
    calls = []
    use_update(
        monkeypatch,
        UpdateResult(UpdateOutcome.UPDATED, 42, action, active_volunteer_count=1),
        calls,
    )

    await line_handler.handle_event(postback_event(data))

    assert calls == [("UV1", 42, action)]
    assert "#42" in recorder.replies[0]


async def test_done_reply_says_closed_and_mentions_others(recorder, monkeypatch):
    use_update(
        monkeypatch,
        UpdateResult(
            UpdateOutcome.UPDATED,
            42,
            AssignmentAction.DONE,
            active_volunteer_count=2,
            incident_closed=True,
        ),
    )

    await line_handler.handle_event(postback_event("action=done&incident_id=42"))

    assert "ปิดเหตุ #42" in recorder.replies[0]
    assert "อีก 2 คน" in recorder.replies[0]
    assert "1362" in recorder.replies[0]


@pytest.mark.parametrize("outcome", [UpdateOutcome.UPDATED, UpdateOutcome.UNCHANGED])
async def test_arrived_reply_shows_done_and_withdraw_buttons(monkeypatch, outcome):
    sent = []

    async def fake_reply(reply_token, messages):
        sent.append(messages)

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr(line_handler, "reply_message", fake_reply)
    monkeypatch.setattr(line_handler, "SessionLocal", fake_session)
    use_update(
        monkeypatch,
        UpdateResult(
            outcome,
            42,
            AssignmentAction.ARRIVED,
            assignment_status=AssignmentStatus.ARRIVED,
        ),
    )

    await line_handler.handle_event(postback_event("action=arrived&incident_id=42"))

    footer = sent[0].to_dict()["contents"]["footer"]["contents"]
    assert [button["action"]["label"] for button in footer] == [
        "เรียบร้อยแล้ว",
        "ถอนตัว",
    ]
    actions = [parse_postback_data(button["action"]["data"]) for button in footer]
    assert actions == [("done", 42), ("withdraw", 42)]


async def test_withdraw_reply_is_plain_text_with_rejoin_hint(recorder, monkeypatch):
    use_update(
        monkeypatch,
        UpdateResult(
            UpdateOutcome.UPDATED,
            42,
            AssignmentAction.WITHDRAW,
            assignment_status=AssignmentStatus.WITHDRAWN,
            active_volunteer_count=1,
        ),
    )

    await line_handler.handle_event(postback_event("action=withdraw&incident_id=42"))

    assert "ฉันขอไป" in recorder.replies[0]


async def test_all_withdrawn_reply_says_redispatched(recorder, monkeypatch):
    use_update(
        monkeypatch,
        UpdateResult(
            UpdateOutcome.UPDATED, 42, AssignmentAction.WITHDRAW, all_withdrawn=True
        ),
    )

    await line_handler.handle_event(postback_event("action=withdraw&incident_id=42"))

    assert "ไม่มีใครรับ" in recorder.replies[0]


@pytest.mark.parametrize(
    ("status", "expected"),
    [(AssignmentStatus.WITHDRAWN, "ฉันขอไป"), (AssignmentStatus.DONE, "เสร็จ")],
)
async def test_invalid_transition_reply(recorder, monkeypatch, status, expected):
    use_update(
        monkeypatch,
        UpdateResult(
            UpdateOutcome.INVALID_TRANSITION,
            42,
            AssignmentAction.ARRIVED,
            assignment_status=status,
        ),
    )

    await line_handler.handle_event(postback_event("action=arrived&incident_id=42"))

    assert expected in recorder.replies[0]


@pytest.mark.parametrize("reason", list(DispatchReason))
def test_flex_header_per_dispatch_reason(reason):
    message = build_incident_alert(target(reason=reason)).to_dict()

    assert "#42" in message["contents"]["header"]["contents"][0]["text"]


@pytest.mark.parametrize(
    ("full_name", "expected"),
    [("สมศักดิ์ ใจดี", "สมศักดิ์"), ("   ", "จิตอาสา"), ("", "จิตอาสา")],
)
def test_first_name_never_crashes(full_name, expected):
    assert first_name(full_name) == expected
