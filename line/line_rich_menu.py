import logging
from dataclasses import dataclass

from linebot.v3.messaging import (
    RichMenuArea,
    RichMenuBounds,
    RichMenuRequest,
    RichMenuSize,
    URIAction,
)
from linebot.v3.messaging.api_client import ApiException

from line.line_service import LineService

logger = logging.getLogger(__name__)

REPORT_MENU_NAME = "paifahsai-report"
REPORT_CHAT_BAR_TEXT = "แจ้งไฟป่า"
REPORT_AREA_LABEL = "แจ้งเหตุไฟป่า"


@dataclass(frozen=True)
class RichMenuInfo:
    rich_menu_id: str
    name: str
    chat_bar_text: str
    is_default: bool


def build_report_menu(uri: str, width: int, height: int) -> RichMenuRequest:
    return RichMenuRequest(
        size=RichMenuSize(width=width, height=height),
        selected=True,
        name=REPORT_MENU_NAME,
        chatBarText=REPORT_CHAT_BAR_TEXT,
        areas=[
            RichMenuArea(
                bounds=RichMenuBounds(x=0, y=0, width=width, height=height),
                action=URIAction(label=REPORT_AREA_LABEL, uri=uri),
            )
        ],
    )


async def default_rich_menu_id(line: LineService) -> str | None:
    try:
        response = await line.api.get_default_rich_menu_id()
    except ApiException as error:
        if error.status == 404:
            return None
        raise
    return response.rich_menu_id


async def list_rich_menus(line: LineService) -> list[RichMenuInfo]:
    response = await line.retry(line.api.get_rich_menu_list)
    default_id = await default_rich_menu_id(line)
    return [
        RichMenuInfo(
            rich_menu_id=menu.rich_menu_id,
            name=menu.name,
            chat_bar_text=menu.chat_bar_text,
            is_default=menu.rich_menu_id == default_id,
        )
        for menu in response.richmenus
    ]


async def deploy_report_menu(
    line: LineService,
    uri: str,
    image: bytes,
    content_type: str,
    width: int,
    height: int,
) -> str:
    request = build_report_menu(uri, width, height)
    await line.retry(line.api.validate_rich_menu_object, request)
    created = await line.retry(line.api.create_rich_menu, request)
    rich_menu_id = created.rich_menu_id
    logger.info("rich menu created: id=%s uri=%s", rich_menu_id, uri)

    try:
        await line.retry(
            line.blob_api.set_rich_menu_image,
            rich_menu_id,
            image,
            _headers={"Content-Type": content_type},
        )
        await line.retry(line.api.set_default_rich_menu, rich_menu_id)
    except Exception:
        logger.error(
            "rich menu setup failed, deleting half-made menu: id=%s", rich_menu_id
        )
        await line.retry(line.api.delete_rich_menu, rich_menu_id)
        raise

    logger.info("rich menu set as default: id=%s", rich_menu_id)
    return rich_menu_id


async def delete_rich_menu(line: LineService, rich_menu_id: str) -> None:
    await line.retry(line.api.delete_rich_menu, rich_menu_id)
    logger.info("rich menu deleted: id=%s", rich_menu_id)
