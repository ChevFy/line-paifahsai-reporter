import argparse
import asyncio
import io
import sys
from pathlib import Path

from PIL import Image

from core.log_config import setup_logging
from line.line_client import close_line_bot_api, get_line_service
from line.line_rich_menu import (
    REPORT_MENU_NAME,
    delete_rich_menu,
    deploy_report_menu,
    list_rich_menus,
)
from services.rich_menu_image import MAX_IMAGE_BYTES, render_report_menu

DEFAULT_FONT = "/System/Library/Fonts/Supplemental/SukhumvitSet.ttc"
SUKHUMVIT_BOLD = 5
SUKHUMVIT_MEDIUM = 3
LIFF_PREFIX = "https://liff.line.me/"
IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg"}


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def load_image(image_path: str | None, font: str) -> tuple[bytes, str, int, int]:
    if image_path is None:
        data = render_report_menu(font, SUKHUMVIT_BOLD, SUKHUMVIT_MEDIUM)
    else:
        data = Path(image_path).read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        fail(f"image is {len(data)} bytes, LINE allows at most {MAX_IMAGE_BYTES}")

    with Image.open(io.BytesIO(data)) as image:
        content_type = IMAGE_TYPES.get(image.format)
        width, height = image.size
    if content_type is None:
        fail("rich menu image must be PNG or JPEG")
    if not 800 <= width <= 2500 or height < 250 or width / height < 1.45:
        fail(f"image size {width}x{height} not allowed by LINE rich menu")
    return data, content_type, width, height


async def show() -> None:
    menus = await list_rich_menus(get_line_service())
    if not menus:
        print("no rich menus")
    for menu in menus:
        marker = "*" if menu.is_default else " "
        print(f"{marker} {menu.rich_menu_id}\t{menu.name}\t{menu.chat_bar_text}")


async def deploy(uri: str, image_path: str | None, font: str) -> None:
    if not uri.startswith("https://"):
        fail("uri must be https")
    if not uri.startswith(LIFF_PREFIX):
        print(
            f"warning: {uri} is not a {LIFF_PREFIX} URL. Opening the endpoint "
            "directly skips LIFF login, so reports fail without an ID token.",
            file=sys.stderr,
        )

    data, content_type, width, height = load_image(image_path, font)
    line = get_line_service()
    previous = [
        menu for menu in await list_rich_menus(line) if menu.name == REPORT_MENU_NAME
    ]
    rich_menu_id = await deploy_report_menu(
        line, uri, data, content_type, width, height
    )
    print(f"default rich menu: {rich_menu_id} -> {uri}")

    for menu in previous:
        await delete_rich_menu(line, menu.rich_menu_id)
        print(f"deleted old menu: {menu.rich_menu_id}")


async def remove(rich_menu_id: str) -> None:
    await delete_rich_menu(get_line_service(), rich_menu_id)
    print(f"deleted: {rich_menu_id}")


def preview(out: str, font: str) -> None:
    data, _, width, height = load_image(None, font)
    Path(out).write_bytes(data)
    print(f"wrote {out} ({width}x{height}, {len(data)} bytes)")


async def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.rich_menu")
    parser.add_argument("--font", default=DEFAULT_FONT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    preview_parser = commands.add_parser("preview")
    preview_parser.add_argument("--out", default="rich_menu_preview.png")
    deploy_parser = commands.add_parser("deploy")
    deploy_parser.add_argument("--uri", required=True)
    deploy_parser.add_argument("--image", help="custom PNG/JPEG instead of rendered")
    delete_parser = commands.add_parser("delete")
    delete_parser.add_argument("rich_menu_id")

    args = parser.parse_args()
    try:
        if args.command == "list":
            await show()
        elif args.command == "preview":
            preview(args.out, args.font)
        elif args.command == "deploy":
            await deploy(args.uri, args.image, args.font)
        else:
            await remove(args.rich_menu_id)
    finally:
        await close_line_bot_api()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
