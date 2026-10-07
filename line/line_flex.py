from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    FlexBox,
    FlexBubble,
    FlexButton,
    FlexMessage,
    FlexText,
    PostbackAction,
    TextMessage,
    URIAction,
)

from services.assignments import AssignmentAction
from services.dispatch import DispatchReason, DispatchTarget
from services.notifications import AssignmentSummary

ACTION_ACCEPT = "accept"
KNOWN_ACTIONS = {ACTION_ACCEPT} | {action.value for action in AssignmentAction}
BANGKOK = ZoneInfo("Asia/Bangkok")
MAX_DESCRIPTION_LENGTH = 300
MAX_ALT_TEXT_LENGTH = 400
FIRE_COLOR = "#D9480F"
EMERGENCY_PHONE = "1362"
HEADERS = {
    DispatchReason.INITIAL: "🔥 แจ้งเหตุไฟป่า #{id}",
    DispatchReason.ESCALATION: "⚠️ ยังไม่มีใครรับ! ไฟป่า #{id}",
    DispatchReason.ALL_WITHDRAWN: "⚠️ ต้องการคนเพิ่ม ไฟป่า #{id}",
}
CONTROL_BUTTONS = (
    (AssignmentAction.ARRIVED, "ถึงแล้ว", "primary"),
    (AssignmentAction.DONE, "เสร็จของฉัน", "primary"),
    (AssignmentAction.WITHDRAW, "ถอนตัว", "secondary"),
)


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
                    text=HEADERS[target.reason].format(id=target.incident_id),
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
    header = HEADERS[target.reason].format(id=target.incident_id)
    return FlexMessage(
        alt_text=f"{header} {location} กดเพื่อรับงาน",
        contents=bubble,
    )


def build_assignment_controls(incident_id: int, text: str) -> FlexMessage:
    buttons = [
        FlexButton(
            style=style,
            color=FIRE_COLOR if style == "primary" else None,
            action=PostbackAction(
                label=label,
                data=postback_data(action.value, incident_id),
                display_text=f"{label} เหตุ #{incident_id}",
            ),
        )
        for action, label, style in CONTROL_BUTTONS
    ]
    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            contents=[FlexText(text=text, wrap=True, size="sm")],
        ),
        footer=FlexBox(layout="vertical", spacing="sm", contents=buttons),
    )
    return FlexMessage(alt_text=text[:MAX_ALT_TEXT_LENGTH], contents=bubble)


def build_assignment_summary(summary: AssignmentSummary) -> TextMessage:
    count = len(summary.volunteer_names)
    head = f"เหตุ #{summary.incident_id} อ.{summary.district_name}"
    if count == 0:
        return TextMessage(
            text=(
                f"{head}: ตอนนี้ไม่มีจิตอาสารับงาน\n"
                "ถ้าอยู่ใกล้และไปได้ กด \"ฉันขอไป\" ในข้อความแจ้งเหตุ"
            )
        )
    names = ", ".join(name.split()[0] for name in summary.volunteer_names)
    return TextMessage(
        text=(
            f"{head}: มีจิตอาสารับงานแล้ว {count} คน ({names})\n"
            "ถ้าอยู่ใกล้และไปช่วยได้ กด \"ฉันขอไป\" ในข้อความแจ้งเหตุ"
        )
    )


def build_closure_for_reporter(incident_id: int, district_name: str) -> TextMessage:
    return TextMessage(
        text=(
            f"เหตุไฟป่าที่คุณแจ้ง (#{incident_id} อ.{district_name}) "
            "จิตอาสารายงานว่าดับเรียบร้อยแล้ว ขอบคุณที่แจ้งครับ\n"
            f"หากพบไฟปะทุอีก แจ้งใหม่ได้ทันที หรือโทร {EMERGENCY_PHONE}"
        )
    )


def build_closure_for_volunteer(incident_id: int, district_name: str) -> TextMessage:
    return TextMessage(
        text=(
            f"ปิดเหตุ #{incident_id} อ.{district_name} แล้ว "
            "ทุกคนรายงานเสร็จครบ ขอบคุณทุกคนที่ไปช่วยครับ"
        )
    )
