from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    FlexBox,
    FlexBubble,
    FlexButton,
    FlexMessage,
    FlexText,
    PostbackAction,
    URIAction,
)

from services.dispatch import DispatchTarget

ACTION_ACCEPT = "accept"
KNOWN_ACTIONS = {ACTION_ACCEPT}
BANGKOK = ZoneInfo("Asia/Bangkok")
MAX_DESCRIPTION_LENGTH = 300
FIRE_COLOR = "#D9480F"


def postback_data(action: str, incident_id: int) -> str:
    return urlencode({"action": action, "incident_id": incident_id})


def parse_postback_data(data: str) -> tuple[str, int] | None:
    params = parse_qs(data)
    action = params.get("action", [""])[0]
    incident_id = params.get("incident_id", [""])[0]
    if action not in KNOWN_ACTIONS or not incident_id.isdigit():
        return None
    return action, int(incident_id)


def map_url(latitude: float, longitude: float) -> str:
    return (
        "https://www.google.com/maps/search/?api=1&query="
        f"{latitude:.6f},{longitude:.6f}"
    )


def build_incident_alert(target: DispatchTarget) -> FlexMessage:
    reported_at = target.created_at.astimezone(BANGKOK).strftime("%H:%M น.")
    location = f"อ.{target.district_name} จ.{target.province_name}"

    body_contents = [
        FlexText(text=location, weight="bold", size="md", wrap=True),
        FlexText(text=f"แจ้งเมื่อ {reported_at}", size="sm", color="#666666"),
    ]
    if target.description:
        body_contents.append(
            FlexText(
                text=target.description[:MAX_DESCRIPTION_LENGTH],
                size="sm",
                wrap=True,
                margin="md",
            )
        )
    body_contents.append(
        FlexText(
            text=f"พิกัด {target.latitude:.5f}, {target.longitude:.5f}",
            size="xs",
            color="#999999",
            margin="md",
        )
    )

    bubble = FlexBubble(
        header=FlexBox(
            layout="vertical",
            contents=[
                FlexText(
                    text=f"🔥 แจ้งเหตุไฟป่า #{target.incident_id}",
                    weight="bold",
                    size="lg",
                    color=FIRE_COLOR,
                )
            ],
        ),
        body=FlexBox(layout="vertical", spacing="sm", contents=body_contents),
        footer=FlexBox(
            layout="vertical",
            spacing="sm",
            contents=[
                FlexButton(
                    style="primary",
                    color=FIRE_COLOR,
                    action=PostbackAction(
                        label="ฉันขอไป",
                        data=postback_data(ACTION_ACCEPT, target.incident_id),
                        display_text=f"ฉันขอไปเหตุ #{target.incident_id}",
                    ),
                ),
                FlexButton(
                    style="secondary",
                    action=URIAction(
                        label="เปิดแผนที่",
                        uri=map_url(target.latitude, target.longitude),
                    ),
                ),
            ],
        ),
    )
    return FlexMessage(
        alt_text=f"🔥 แจ้งเหตุไฟป่า #{target.incident_id} {location} กดเพื่อรับงาน",
        contents=bubble,
    )
