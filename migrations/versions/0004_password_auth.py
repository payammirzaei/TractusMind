"""Add local username/password authentication fields.

Revision ID: 0004_password_auth
Revises: 0003_oidc_rbac
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_password_auth"
down_revision: str | Sequence[str] | None = "0003_oidc_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _index_names(table_name: str) -> set[str]:
    return {
        str(index["name"])
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def upgrade() -> None:
    columns = _column_names("app_user")
    if "username" not in columns:
        op.add_column("app_user", sa.Column("username", sa.String(length=80), nullable=True))
    if "password_salt" not in columns:
        op.add_column(
            "app_user",
            sa.Column("password_salt", sa.String(length=64), nullable=True),
        )
    if "password_hash" not in columns:
        op.add_column(
            "app_user",
            sa.Column("password_hash", sa.String(length=64), nullable=True),
        )

    if "ux_app_user_username" not in _index_names("app_user"):
        op.create_index("ux_app_user_username", "app_user", ["username"], unique=True)


def downgrade() -> None:
    password_count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM app_user WHERE auth_type = 'password'")
    ).scalar_one()
    if password_count:
        raise RuntimeError("Cannot downgrade 0004_password_auth while password identities exist")

    if "ux_app_user_username" in _index_names("app_user"):
        op.drop_index("ux_app_user_username", table_name="app_user")
    columns = _column_names("app_user")
    for name in ("password_hash", "password_salt", "username"):
        if name in columns:
            op.drop_column("app_user", name)
