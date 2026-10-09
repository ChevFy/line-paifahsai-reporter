import argparse
import asyncio
from datetime import UTC, datetime

from config.config import settings
from core.db import SessionLocal, close_db
from core.log_config import setup_logging
from services.incident_photos import build_photo_page_url, list_incident_photos


async def photos(incident_id: int) -> None:
    async with SessionLocal() as session:
        found = await list_incident_photos(session, incident_id)
    print(f"incident #{incident_id}: {len(found)} photo(s)")
    for photo in found:
        print(f"  report #{photo.report_id}\t{photo.created_at:%Y-%m-%d %H:%M}")
    url = build_photo_page_url(
        settings.PUBLIC_BASE_URL,
        settings.PHOTO_LINK_SECRET,
        incident_id,
        datetime.now(UTC),
    )
    print(url)


async def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.incidents")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("photos").add_argument("incident_id", type=int)

    args = parser.parse_args()
    try:
        await photos(args.incident_id)
    finally:
        await close_db()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
