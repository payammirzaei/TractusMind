"""Add OIDC identities and role-based access control.

Revision ID: 0003_oidc_rbac
Revises: 0002_user_auth
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_oidc_rbac"
down_revision: str | Sequence[str] | None = "0002_user_auth"
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
    added_auth_type = "auth_type" not in columns
    added_role = "role" not in columns
    if added_auth_type:
        op.add_column(
            "app_user",
            sa.Column(
                "auth_type",
                sa.String(length=20),
                nullable=False,
                server_default="api_key",
            ),
        )
    if added_role:
        op.add_column(
            "app_user",
            sa.Column(
                "role",
                sa.String(length=20),
                nullable=False,
                server_default="user",
            ),
        )
    if "oidc_issuer" not in columns:
        op.add_column(
            "app_user",
            sa.Column("oidc_issuer", sa.String(length=500), nullable=True),
        )
    if "oidc_subject" not in columns:
        op.add_column(
            "app_user",
            sa.Column("oidc_subject", sa.String(length=500), nullable=True),
        )

    if added_auth_type:
        op.alter_column("app_user", "auth_type", server_default=None)
    if added_role:
        op.alter_column("app_user", "role", server_default=None)

    op.alter_column(
        "app_user",
        "api_key_prefix",
        existing_type=sa.String(length=16),
        nullable=True,
    )
    op.alter_column(
        "app_user",
        "api_key_hash",
        existing_type=sa.String(length=64),
        nullable=True,
    )

    indexes = _index_names("app_user")
    if "ix_app_user_auth_type" not in indexes:
        op.create_index("ix_app_user_auth_type", "app_user", ["auth_type"])
    if "ix_app_user_role" not in indexes:
        op.create_index("ix_app_user_role", "app_user", ["role"])
    if "ux_app_user_oidc_identity" not in indexes:
        op.create_index(
            "ux_app_user_oidc_identity",
            "app_user",
            ["oidc_issuer", "oidc_subject"],
            unique=True,
        )


def downgrade() -> None:
    oidc_count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM app_user WHERE auth_type = 'oidc'")
    ).scalar_one()
    if oidc_count:
        raise RuntimeError("Cannot downgrade 0003_oidc_rbac while OIDC identities exist")

    indexes = _index_names("app_user")
    if "ux_app_user_oidc_identity" in indexes:
        op.drop_index("ux_app_user_oidc_identity", table_name="app_user")
    if "ix_app_user_role" in indexes:
        op.drop_index("ix_app_user_role", table_name="app_user")
    if "ix_app_user_auth_type" in indexes:
        op.drop_index("ix_app_user_auth_type", table_name="app_user")

    op.alter_column(
        "app_user",
        "api_key_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "app_user",
        "api_key_prefix",
        existing_type=sa.String(length=16),
        nullable=False,
    )
    for name in ("oidc_subject", "oidc_issuer", "role", "auth_type"):
        if name in _column_names("app_user"):
            op.drop_column("app_user", name)
