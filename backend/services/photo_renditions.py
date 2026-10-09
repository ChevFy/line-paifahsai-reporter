import io
from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from PIL import Image, ImageOps, UnidentifiedImageError

FULL_MAX_SIDE = 2048
FULL_QUALITY = 85
PREVIEW_MAX_SIDE = 480
PREVIEW_QUALITY = 75
LINE_PREVIEW_MAX_BYTES = 1024 * 1024
LINE_FULL_MAX_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 60_000_000


class PhotoVariant(StrEnum):
    FULL = "full"
    PREVIEW = "preview"


@dataclass(frozen=True)
class LineRenditions:
    full: bytes
    preview: bytes


class UnreadableImageError(Exception):
    pass


@cache
def register_formats() -> None:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def rendition_key(image_path: str, variant: PhotoVariant) -> str:
    return f"{image_path}.{variant.value}.jpg"


def encode_jpeg(image: Image.Image, max_side: int, quality: int) -> bytes:
    resized = image.copy()
    resized.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    resized.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def render_line_images(data: bytes) -> LineRenditions:
    register_formats()
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise UnreadableImageError(f"{type(error).__name__}: {error}") from error

    full = encode_jpeg(image, FULL_MAX_SIDE, FULL_QUALITY)
    preview = encode_jpeg(image, PREVIEW_MAX_SIDE, PREVIEW_QUALITY)
    if len(full) > LINE_FULL_MAX_BYTES or len(preview) > LINE_PREVIEW_MAX_BYTES:
        raise UnreadableImageError(
            f"rendition too large: full={len(full)} preview={len(preview)}"
        )
    return LineRenditions(full=full, preview=preview)
