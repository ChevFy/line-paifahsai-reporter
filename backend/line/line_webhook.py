import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from linebot.v3 import WebhookParser

from config.config import settings
from core.db import SessionLocal
from jobs.line_events import enqueue_line_event
from jobs.worker import wake_worker

logger = logging.getLogger(__name__)

router = APIRouter()
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)


@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str = Header(None),
):
    body = await request.body()
    if not parser.signature_validator.validate(
        body.decode("utf-8"), x_line_signature or ""
    ):
        logger.warning("LINE webhook rejected: invalid signature")
        raise HTTPException(status_code=400, detail="invalid signature")

    raw_events = json.loads(body).get("events", [])
    if not raw_events:
        return {}

    try:
        async with SessionLocal() as session, session.begin():
            new_count = 0
            for raw_event in raw_events:
                new_count += await enqueue_line_event(session, raw_event)
    except Exception:
        logger.critical(
            "failed to persist LINE webhook events, LINE may redeliver: count=%s",
            len(raw_events),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="failed to persist events")

    logger.info(
        "LINE webhook accepted: events=%s new=%s duplicate=%s",
        len(raw_events),
        new_count,
        len(raw_events) - new_count,
    )
    wake_worker()
    return {}
