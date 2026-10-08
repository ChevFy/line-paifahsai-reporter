import io
from pathlib import Path

import pytest
from PIL import Image

from line.line_rich_menu import (
    REPORT_CHAT_BAR_TEXT,
    build_report_menu,
    deploy_report_menu,
)
from scripts import rich_menu as script
from services.rich_menu_image import EMERGENCY, HEIGHT, WIDTH, render_report_menu

FONT = Path(script.DEFAULT_FONT)
LIFF_URL = "https://liff.line.me/2011591148-vD7leNe5"

needs_font = pytest.mark.skipif(not FONT.exists(), reason="SukhumvitSet font not found")


def test_report_menu_is_one_area_covering_whole_image():
    menu = build_report_menu(LIFF_URL, WIDTH, HEIGHT).to_dict()

    assert menu["selected"] is True
    assert menu["chatBarText"] == REPORT_CHAT_BAR_TEXT
    assert len(REPORT_CHAT_BAR_TEXT) <= 14
    [area] = menu["areas"]
    assert area["bounds"] == {"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT}
    assert area["action"]["type"] == "uri"
    assert area["action"]["uri"] == LIFF_URL


def test_menu_text_tells_people_to_call_1362():
    assert "1362" in EMERGENCY


@needs_font
def test_rendered_menu_fits_line_limits():
    data = render_report_menu(
        str(FONT), script.SUKHUMVIT_BOLD, script.SUKHUMVIT_MEDIUM
    )

    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "PNG"
        assert image.size == (WIDTH, HEIGHT)
    assert len(data) <= 1024 * 1024


@pytest.mark.parametrize(
    ("size", "fmt"),
    [((2500, 2500), "PNG"), ((700, 300), "PNG"), ((2500, 843), "GIF")],
)
def test_custom_image_outside_line_rules_is_rejected(tmp_path, size, fmt):
    path = tmp_path / "menu"
    Image.new("RGB", size, "red").save(path, format=fmt)

    with pytest.raises(SystemExit):
        script.load_image(str(path), str(FONT))


def test_custom_jpeg_is_accepted(tmp_path):
    path = tmp_path / "menu.jpg"
    Image.new("RGB", (1200, 405), "red").save(path, format="JPEG")

    _, content_type, width, height = script.load_image(str(path), str(FONT))

    assert (content_type, width, height) == ("image/jpeg", 1200, 405)


class FakeRichMenuApi:
    def __init__(self, image_error: Exception | None = None):
        self.calls = []
        self.image_error = image_error

    async def validate_rich_menu_object(self, request):
        self.calls.append(("validate",))

    async def create_rich_menu(self, request):
        self.calls.append(("create",))
        return type("Created", (), {"rich_menu_id": "richmenu-1"})()

    async def set_rich_menu_image(self, rich_menu_id, body, **kwargs):
        self.calls.append(("image", rich_menu_id, kwargs.get("_headers")))
        if self.image_error is not None:
            raise self.image_error

    async def set_default_rich_menu(self, rich_menu_id):
        self.calls.append(("default", rich_menu_id))

    async def delete_rich_menu(self, rich_menu_id):
        self.calls.append(("delete", rich_menu_id))


class FakeLine:
    def __init__(self, api: FakeRichMenuApi):
        self.api = api
        self.blob_api = api

    async def retry(self, operation, *args, **kwargs):
        return await operation(*args, **kwargs)


@pytest.mark.anyio
async def test_deploy_sends_image_content_type_and_sets_default():
    api = FakeRichMenuApi()

    rich_menu_id = await deploy_report_menu(
        FakeLine(api), LIFF_URL, b"png", "image/png", WIDTH, HEIGHT
    )

    assert rich_menu_id == "richmenu-1"
    assert ("image", "richmenu-1", {"Content-Type": "image/png"}) in api.calls
    assert api.calls[-1] == ("default", "richmenu-1")


@pytest.mark.anyio
async def test_failed_image_upload_deletes_half_made_menu():
    api = FakeRichMenuApi(image_error=RuntimeError("upload failed"))

    with pytest.raises(RuntimeError):
        await deploy_report_menu(
            FakeLine(api), LIFF_URL, b"png", "image/png", WIDTH, HEIGHT
        )

    assert api.calls[-1] == ("delete", "richmenu-1")
    assert not any(call[0] == "default" for call in api.calls)
