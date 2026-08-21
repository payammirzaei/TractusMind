import argparse
import asyncio
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.auth.store import AuthStore, UserRole
from app.core.config import get_settings
from app.db.schema import verify_database_revision
from app.infra.postgres import create_postgres_engine

CORE_BASELINE_TABLES = {
    "source_state",
    "source_file_state",
    "ingestion_run",
    "conversation",
    "answer_interaction",
    "answer_feedback",
    "quality_review",
    "regression_case",
}
MANAGED_TABLES = CORE_BASELINE_TABLES | {"app_user"}


def _config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_database_url)
    return config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tractusmind-db")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upgrade = subparsers.add_parser("upgrade", help="Upgrade the database schema")
    upgrade.add_argument("revision", nargs="?", default="head")

    downgrade = subparsers.add_parser("downgrade", help="Downgrade the database schema")
    downgrade.add_argument("revision")

    stamp = subparsers.add_parser("stamp", help="Stamp a legacy database without running DDL")
    stamp.add_argument("revision")

    subparsers.add_parser(
        "bootstrap",
        help="Adopt a complete legacy schema or upgrade a versioned/fresh database",
    )
    subparsers.add_parser("current", help="Show the current database revision")
    subparsers.add_parser("history", help="Show migration history")
    subparsers.add_parser("check", help="Fail unless the database is at application head")
    subparsers.add_parser(
        "drift",
        help="Fail when ORM metadata differs from the migrated database schema",
    )

    password_user = subparsers.add_parser(
        "password-user",
        help="Create or convert one local password identity using a password from the environment",
    )
    password_user.add_argument("--username", required=True)
    password_user.add_argument("--display-name", required=True)
    password_user.add_argument("--role", choices=[role.value for role in UserRole], default="user")
    password_user.add_argument("--user-id")
    password_user.add_argument("--password-env", default="TRACTUSMIND_PASSWORD")
    return parser


async def _check() -> None:
    engine = create_postgres_engine(get_settings())
    try:
        revision = await verify_database_revision(engine)
    finally:
        await engine.dispose()
    print(revision)


async def _table_names() -> set[str]:
    engine = create_postgres_engine(get_settings())
    try:
        async with engine.connect() as connection:
            names = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
    finally:
        await engine.dispose()
    return {str(name) for name in names}


async def _password_user(args: argparse.Namespace) -> None:
    password = os.environ.get(args.password_env)
    if not password:
        raise SystemExit(f"Password environment variable is missing: {args.password_env}")

    engine = create_postgres_engine(get_settings())
    try:
        store = AuthStore(engine)
        identity = await store.set_password_user(
            username=args.username,
            password=password,
            display_name=args.display_name,
            role=UserRole(args.role),
            user_id=args.user_id,
        )
    finally:
        await engine.dispose()
    print(f"password identity ready: {identity.username} ({identity.user_id}) [{identity.role.value}]")


def _bootstrap(config: Config) -> None:
    tables = asyncio.run(_table_names())
    if "alembic_version" in tables:
        command.upgrade(config, "head")
        return

    managed = tables & MANAGED_TABLES
    if not managed:
        command.upgrade(config, "head")
        return

    missing = CORE_BASELINE_TABLES - tables
    if missing:
        joined = ", ".join(sorted(missing))
        raise SystemExit(
            "Refusing to bootstrap a partial legacy schema. "
            f"Missing managed tables: {joined}."
        )

    command.stamp(config, "0001_core_schema")
    command.upgrade(config, "head")


def main() -> None:
    args = _parser().parse_args()
    config = _config()
    if args.command == "upgrade":
        command.upgrade(config, args.revision)
    elif args.command == "downgrade":
        command.downgrade(config, args.revision)
    elif args.command == "stamp":
        command.stamp(config, args.revision)
    elif args.command == "bootstrap":
        _bootstrap(config)
    elif args.command == "current":
        command.current(config, verbose=True)
    elif args.command == "history":
        command.history(config, verbose=True)
    elif args.command == "drift":
        command.check(config)
    elif args.command == "password-user":
        asyncio.run(_password_user(args))
    else:
        asyncio.run(_check())


if __name__ == "__main__":
    main()
