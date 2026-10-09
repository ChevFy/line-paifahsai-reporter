import io

from PIL import Image, ImageDraw, ImageFont

WIDTH = 2500
HEIGHT = 843
BACKGROUND = "#D9480F"
FOREGROUND = "#FFFFFF"
EMERGENCY_BACKGROUND = "#7A1F00"
EMERGENCY_PHONE = "1362"
MAX_IMAGE_BYTES = 1024 * 1024

TITLE = "แจ้งเหตุไฟป่า"
SUBTITLE = "ปักหมุดตำแหน่งไฟ + ถ่ายรูป ส่งถึงจิตอาสาในพื้นที่"
EMERGENCY = f"เหตุด่วน โทร {EMERGENCY_PHONE} (ศูนย์รับแจ้งไฟป่า)"


def centered(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill: str) -> None:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (right - left)) // 2, y), text, font=font, fill=fill)


def render_report_menu(
    font_path: str,
    bold_index: int = 0,
    regular_index: int = 0,
) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    bold = ImageFont.truetype(font_path, 230, index=bold_index)
    regular = ImageFont.truetype(font_path, 80, index=regular_index)
    emergency = ImageFont.truetype(font_path, 90, index=bold_index)

    centered(draw, 110, TITLE, bold, FOREGROUND)
    centered(draw, 440, SUBTITLE, regular, FOREGROUND)
    draw.rectangle((0, 640, WIDTH, HEIGHT), fill=EMERGENCY_BACKGROUND)
    centered(draw, 675, EMERGENCY, emergency, FOREGROUND)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    data = buffer.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"rich menu image too large: {len(data)} bytes")
    return data
