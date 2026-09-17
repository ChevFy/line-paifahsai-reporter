from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from config.config import settings
from line.line_handler import handle_event


from fastapi import APIRouter, Request, Header, HTTPException
from fastapi import BackgroundTasks

router = APIRouter()
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)


@router.post("/webhook")
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(None),
):
    body = await request.body()
    try:
        events = parser.parse(body.decode("utf-8"), x_line_signature or "")
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="invalid signature")

    for event in events:
        background_tasks.add_task(handle_event, event)
    return {}
