"""Add API-key users and owned conversations.

Revision ID: 0002_user_auth
Revises: 0001_core_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_user_auth"
down_revision: str | Sequence[str] | None = "0001_core_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


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
    if "app_user" not in _table_names():
        op.create_table(
            "app_user",
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("api_key_prefix", sa.String(length=16), nullable=False),
            sa.Column("api_key_hash", sa.String(length=64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("user_id"),
        )

    user_indexes = _index_names("app_user")
    if "ix_app_user_api_key_prefix" not in user_indexes:
        op.create_index(
            "ix_app_user_api_key_prefix",
            "app_user",
            ["api_key_prefix"],
        )
    if "ix_app_user_api_key_hash" not in user_indexes:
        op.create_index(
            "ix_app_user_api_key_hash",
            "app_user",
            ["api_key_hash"],
            unique=True,
        )
    if "ix_app_user_enabled" not in user_indexes:
        op.create_index("ix_app_user_enabled", "app_user", ["enabled"])
    if "ix_app_user_created_at" not in user_indexes:
        op.create_index("ix_app_user_created_at", "app_user", ["created_at"])

    if "owner_user_id" not in _column_names("conversation"):
        op.add_column(
            "conversation",
            sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        )

    conversation_indexes = _index_names("conversation")
    if "ix_conversation_owner_user_id" not in conversation_indexes:
        op.create_index(
            "ix_conversation_owner_user_id",
            "conversation",
            ["owner_user_id"],
        )

    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("conversation")
    owner_fk_exists = any(
        foreign_key.get("constrained_columns") == ["owner_user_id"]
        and foreign_key.get("referred_table") == "app_user"
        for foreign_key in foreign_keys
    )
    if not owner_fk_exists:
        op.create_foreign_key(
            "fk_conversation_owner_user_id_app_user",
            "conversation",
            "app_user",
            ["owner_user_id"],
            ["user_id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    has_owner = (
        "conversation" in _table_names()
        and "owner_user_id" in _column_names("conversation")
    )
    if has_owner:
        foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("conversation")
        for foreign_key in foreign_keys:
            if foreign_key.get("constrained_columns") != ["owner_user_id"]:
                continue
            name = foreign_key.get("name")
            if name:
                op.drop_constraint(str(name), "conversation", type_="foreignkey")
        if "ix_conversation_owner_user_id" in _index_names("conversation"):
            op.drop_index("ix_conversation_owner_user_id", table_name="conversation")
        op.drop_column("conversation", "owner_user_id")

    if "app_user" in _table_names():
        op.drop_table("app_user")
