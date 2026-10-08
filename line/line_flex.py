from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    FlexBox,
    FlexBubble,
    FlexButton,
    FlexMessage,
    FlexText,
    ImageMessage,
    PostbackAction,
    TextMessage,
    URIAction,
)

from models import VolunteerStatus
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
UNNAMED_VOLUNTEER = "จิตอาสา"
HEADERS = {
    DispatchReason.INITIAL: "🔥 แจ้งเหตุไฟป่า #{id}",
    DispatchReason.ESCALATION: "⚠️ ยังไม่มีใครรับ! ไฟป่า #{id}",
    DispatchReason.ALL_WITHDRAWN: "⚠️ ต้องการคนเพิ่ม ไฟป่า #{id}",
}
CONTROL_BUTTONS = {
    AssignmentAction.ARRIVED: ("ถึงแล้ว", "primary"),
    AssignmentAction.DONE: ("เรียบร้อยแล้ว", "primary"),
    AssignmentAction.WITHDRAW: ("ถอนตัว", "secondary"),
}
EN_ROUTE_ACTIONS = (
    AssignmentAction.ARRIVED,
    AssignmentAction.DONE,
    AssignmentAction.WITHDRAW,
)
ON_SITE_ACTIONS = (AssignmentAction.DONE, AssignmentAction.WITHDRAW)
DONE_LABEL = CONTROL_BUTTONS[AssignmentAction.DONE][0]


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


def build_incident_photo(full_url: str, preview_url: str) -> ImageMessage:
    return ImageMessage(
        original_content_url=full_url,
        preview_image_url=preview_url,
    )


def build_assignment_controls(
    incident_id: int,
    text: str,
    actions: tuple[AssignmentAction, ...] = EN_ROUTE_ACTIONS,
) -> FlexMessage:
    buttons = []
    for action in actions:
        label, style = CONTROL_BUTTONS[action]
        buttons.append(
            FlexButton(
                style=style,
                color=FIRE_COLOR if style == "primary" else None,
                action=PostbackAction(
                    label=label,
                    data=postback_data(action.value, incident_id),
                    display_text=f"{label} เหตุ #{incident_id}",
                ),
            )
        )
    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            contents=[FlexText(text=text, wrap=True, size="sm")],
        ),
        footer=FlexBox(layout="vertical", spacing="sm", contents=buttons),
    )
    return FlexMessage(alt_text=text[:MAX_ALT_TEXT_LENGTH], contents=bubble)


def first_name(full_name: str) -> str:
    parts = full_name.split()
    return parts[0] if parts else UNNAMED_VOLUNTEER


def first_names(full_names: list[str]) -> str:
    return ", ".join(first_name(name) for name in full_names)


def build_assignment_summary(summary: AssignmentSummary) -> TextMessage:
    count = len(summary.volunteer_names)
    lines = [f"เหตุ #{summary.incident_id} อ.{summary.district_name}"]
    if summary.joined_names:
        lines.append(f"➕ ขอไป: {first_names(summary.joined_names)}")
    if summary.withdrawn_names:
        lines.append(f"➖ ถอนตัว: {first_names(summary.withdrawn_names)}")
    if count == 0:
        lines.append("ตอนนี้ไม่มีจิตอาสารับงาน")
        lines.append("ถ้าอยู่ใกล้และไปได้ กด \"ฉันขอไป\" ในข้อความแจ้งเหตุ")
    else:
        lines.append(
            f"ตอนนี้มีจิตอาสารับงาน {count} คน: {first_names(summary.volunteer_names)}"
        )
        lines.append("ถ้าอยู่ใกล้และไปช่วยได้ กด \"ฉันขอไป\" ในข้อความแจ้งเหตุ")
    return TextMessage(text="\n".join(lines))


def build_closure_for_reporter(incident_id: int, district_name: str) -> TextMessage:
    return TextMessage(
        text=(
            f"เหตุไฟป่าที่คุณแจ้ง (#{incident_id} อ.{district_name}) "
            "จิตอาสารายงานว่าดับเรียบร้อยแล้ว ขอบคุณที่แจ้งครับ\n"
            f"หากพบไฟปะทุอีก แจ้งใหม่ได้ทันที หรือโทร {EMERGENCY_PHONE}"
        )
    )


def build_volunteer_status_notice(
    status: VolunteerStatus, district_name: str
) -> TextMessage | None:
    if status == VolunteerStatus.APPROVED:
        text = (
            f"แอดมินอนุมัติคุณเป็นจิตอาสาแล้ว คุณจะได้รับแจ้งเหตุไฟป่าใน อ.{district_name}\n"
            "เมื่อได้รับแจ้ง ถ้าอยู่ใกล้และไปได้ กด \"ฉันขอไป\" ในข้อความแจ้งเหตุ"
        )
    elif status == VolunteerStatus.REJECTED:
        text = "การลงทะเบียนจิตอาสาไม่ผ่านการอนุมัติ หากมีข้อสงสัยกรุณาติดต่อแอดมิน"
    elif status == VolunteerStatus.SUSPENDED:
        text = (
            "บัญชีจิตอาสาของคุณถูกระงับชั่วคราว จะไม่ได้รับแจ้งเหตุจนกว่าแอดมินจะเปิดใหม่ "
            "หากมีข้อสงสัยกรุณาติดต่อแอดมิน"
        )
    else:
        return None
    return TextMessage(text=text)


def build_closure_for_volunteer(
    incident_id: int,
    district_name: str,
    closed_by_name: str | None = None,
) -> TextMessage:
    closer = first_name(closed_by_name) if closed_by_name else UNNAMED_VOLUNTEER
    return TextMessage(
        text=(
            f"ปิดเหตุ #{incident_id} อ.{district_name} แล้ว "
            f"{closer} กด \"{DONE_LABEL}\" ขอบคุณทุกคนที่ไปช่วยครับ\n"
            f"ถ้ายังอยู่หน้างานแล้วไฟยังไม่ดับ โทร {EMERGENCY_PHONE} ทันที"
        )
    )
