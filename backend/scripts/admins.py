import argparse
import asyncio
import getpass
import sys
from datetime import UTC, datetime

from core.db import SessionLocal, close_db
from core.log_config import setup_logging
from services.admin_auth import (
    AdminUserExistsError,
    AdminUserNotFoundError,
    InvalidPasswordError,
    create_admin,
    list_admins,
    set_admin_active,
    set_admin_password,
    validate_password,
)


def prompt_password() -> str:
    password = getpass.getpass("password: ")
    validate_password(password)
    if getpass.getpass("confirm password: ") != password:
        raise InvalidPasswordError("passwords do not match")
    return password


async def show() -> None:
    async with SessionLocal() as session:
        admins = await list_admins(session)
    if not admins:
        print("no admins")
    for admin in admins:
        last_login = (
            f"{admin.last_login_at:%Y-%m-%d %H:%M}" if admin.last_login_at else "-"
        )
        print(
            f"#{admin.id}\t{admin.username}\t"
            f"{'active' if admin.is_active else 'disabled'}\tlast_login={last_login}"
        )


async def create(username: str) -> None:
    password = prompt_password()
    async with SessionLocal() as session, session.begin():
        admin = await create_admin(session, username, password)
    print(f"#{admin.id} {admin.username} created")


async def change_password(username: str) -> None:
    password = prompt_password()
    async with SessionLocal() as session, session.begin():
        admin = await set_admin_password(
            session, username, password, datetime.now(UTC)
        )
    print(f"#{admin.id} {admin.username} password changed, all sessions revoked")


async def set_active(username: str, active: bool) -> None:
    async with SessionLocal() as session, session.begin():
        admin = await set_admin_active(session, username, active, datetime.now(UTC))
    state = "enabled" if active else "disabled, all sessions revoked"
    print(f"#{admin.id} {admin.username} {state}")


async def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.admins")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for name in ("create", "set-password", "disable", "enable"):
        commands.add_parser(name).add_argument("username")

    args = parser.parse_args()
    try:
        if args.command == "list":
            await show()
        elif args.command == "create":
            await create(args.username)
        elif args.command == "set-password":
            await change_password(args.username)
        else:
            await set_active(args.username, args.command == "enable")
    except (InvalidPasswordError, AdminUserExistsError, AdminUserNotFoundError) as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
