import argparse
import asyncio

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.db.schema import verify_database_revision
from app.infra.postgres import create_postgres_engine


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

    subparsers.add_parser("current", help="Show the current database revision")
    subparsers.add_parser("history", help="Show migration history")
    subparsers.add_parser("check", help="Fail unless the database is at application head")
    return parser


async def _check() -> None:
    engine = create_postgres_engine(get_settings())
    try:
        revision = await verify_database_revision(engine)
    finally:
        await engine.dispose()
    print(revision)


def main() -> None:
    args = _parser().parse_args()
    config = _config()
    if args.command == "upgrade":
        command.upgrade(config, args.revision)
    elif args.command == "downgrade":
        command.downgrade(config, args.revision)
    elif args.command == "stamp":
        command.stamp(config, args.revision)
    elif args.command == "current":
        command.current(config, verbose=True)
    elif args.command == "history":
        command.history(config, verbose=True)
    else:
        asyncio.run(_check())


if __name__ == "__main__":
    main()
