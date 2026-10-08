import argparse
import asyncio
import sys

import sqlalchemy as sa

from config.config import settings
from core.db import SessionLocal, close_db
from core.log_config import setup_logging
from models import (
    AdminAlert,
    Assignment,
    Incident,
    IncidentEvent,
    Job,
    LineUser,
    Report,
)

RESET_TABLES = (
    Report.__tablename__,
    Incident.__tablename__,
    IncidentEvent.__tablename__,
    Assignment.__tablename__,
    Job.__tablename__,
    AdminAlert.__tablename__,
)


def target_label() -> str:
    return f"{settings.POSTGRES_DB} @ {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}"


async def count_rows() -> dict[str, int]:
    async with SessionLocal() as session:
        return {
            table: (
                await session.execute(sa.text(f"SELECT count(*) FROM {table}"))
            ).scalar_one()
            for table in RESET_TABLES
        }


async def reset() -> None:
    async with SessionLocal() as session, session.begin():
        await session.execute(
            sa.text(f"TRUNCATE {', '.join(RESET_TABLES)} CONTINUE IDENTITY CASCADE")
        )
        await session.execute(
            sa.update(LineUser).values(report_count=0, false_report_count=0)
        )


def confirmed(confirm: str | None) -> bool:
    if confirm is not None:
        return confirm == settings.POSTGRES_DB
    if not sys.stdin.isatty():
        return False
    typed = input(f"type the database name ({settings.POSTGRES_DB}) to confirm: ")
    return typed.strip() == settings.POSTGRES_DB


async def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.dev_reset",
        description=(
            "Wipe reports, incidents, events, assignments, jobs and admin alerts. "
            "Keeps districts, line_users, volunteers and admin accounts. "
            "Images in object storage are not deleted. IDs keep counting up so "
            "LINE retry keys derived from incident IDs never repeat."
        ),
    )
    parser.add_argument(
        "--confirm",
        metavar="DB_NAME",
        help="non-interactive confirmation; must equal POSTGRES_DB",
    )
    args = parser.parse_args()

    try:
        before = await count_rows()
        print(f"target: {target_label()}")
        for table, count in before.items():
            print(f"  {table}: {count} rows")

        if not confirmed(args.confirm):
            print("aborted: database name did not match", file=sys.stderr)
            sys.exit(1)

        await reset()
        after = await count_rows()
        print(f"reset done: {sum(before.values())} rows removed")
        leftover = {table: count for table, count in after.items() if count}
        if leftover:
            print(f"error: rows remain after reset: {leftover}", file=sys.stderr)
            sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
