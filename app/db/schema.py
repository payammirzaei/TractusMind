from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

CURRENT_DATABASE_REVISION = "0002_user_auth"


class DatabaseSchemaError(RuntimeError):
    pass


async def verify_database_revision(engine: AsyncEngine) -> str:
    """Require the database to be migrated to the application head revision."""

    try:
        async with engine.connect() as connection:
            rows = await connection.execute(text("SELECT version_num FROM alembic_version"))
            revisions = [str(value) for value in rows.scalars().all()]
    except SQLAlchemyError as exc:
        raise DatabaseSchemaError(
            "Database migration state is unavailable. Run `tractusmind-db bootstrap`."
        ) from exc

    if revisions != [CURRENT_DATABASE_REVISION]:
        current = ", ".join(revisions) if revisions else "unversioned"
        raise DatabaseSchemaError(
            "Database schema is not current: "
            f"expected {CURRENT_DATABASE_REVISION}, found {current}. "
            "Run `tractusmind-db bootstrap`."
        )
    return CURRENT_DATABASE_REVISION
