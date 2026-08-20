from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.cli import CORE_BASELINE_TABLES, MANAGED_TABLES
from app.db.schema import CURRENT_DATABASE_REVISION


def test_alembic_head_matches_application_revision() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_current_head() == CURRENT_DATABASE_REVISION


def test_migration_chain_contains_core_and_user_auth_revisions() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revisions = {revision.revision: revision for revision in script.walk_revisions()}

    assert "0001_core_schema" in revisions
    assert "0002_user_auth" in revisions
    assert revisions["0002_user_auth"].down_revision == "0001_core_schema"


def test_bootstrap_managed_table_contract_includes_full_core_schema() -> None:
    assert CORE_BASELINE_TABLES <= MANAGED_TABLES
    assert "conversation" in CORE_BASELINE_TABLES
    assert "source_state" in CORE_BASELINE_TABLES
    assert "quality_review" in CORE_BASELINE_TABLES
    assert "app_user" in MANAGED_TABLES
