import argparse
import asyncio
from datetime import UTC, datetime

from core.db import SessionLocal, close_db
from core.log_config import setup_logging
from models import VolunteerStatus
from services.volunteers import STATUS_ACTIONS, list_volunteers, set_volunteer_status


async def show(status: VolunteerStatus | None) -> None:
    async with SessionLocal() as session:
        volunteers = await list_volunteers(session, status)
    if not volunteers:
        print("no volunteers")
    for volunteer in volunteers:
        print(
            f"#{volunteer.id}\t{volunteer.status}\t{volunteer.district_code}\t"
            f"{volunteer.full_name}\t{volunteer.phone}\t{volunteer.created_at:%Y-%m-%d %H:%M}"
        )


async def change(volunteer_id: int, status: VolunteerStatus) -> None:
    async with SessionLocal() as session, session.begin():
        volunteer = await set_volunteer_status(
            session, volunteer_id, status, datetime.now(UTC), actor="cli"
        )
    print(f"#{volunteer.id} {volunteer.full_name} -> {volunteer.status}")


async def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.volunteers")
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list")
    list_parser.add_argument(
        "--status", choices=[status.value for status in VolunteerStatus]
    )
    for name in STATUS_ACTIONS:
        commands.add_parser(name).add_argument("volunteer_id", type=int)

    args = parser.parse_args()
    try:
        if args.command == "list":
            await show(VolunteerStatus(args.status) if args.status else None)
        else:
            await change(args.volunteer_id, STATUS_ACTIONS[args.command])
    finally:
        await close_db()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
