"""Create the TractusMind core schema through V14.

Revision ID: 0001_core_schema
Revises:
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_core_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_state",
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("component", sa.String(length=128), nullable=False),
        sa.Column("version_ref", sa.String(length=255), nullable=False),
        sa.Column("snapshot_commit_sha", sa.String(length=64), nullable=False),
        sa.Column("last_successful_run_id", sa.String(length=36), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_index(
        "ix_source_state_snapshot_commit_sha",
        "source_state",
        ["snapshot_commit_sha"],
    )

    op.create_table(
        "source_file_state",
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("blob_sha", sa.String(length=64), nullable=False),
        sa.Column("content_commit_sha", sa.String(length=64), nullable=False),
        sa.Column("last_seen_snapshot_commit_sha", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source_state.source_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("source_id", "path"),
    )
    op.create_index("ix_source_file_state_blob_sha", "source_file_state", ["blob_sha"])
    op.create_index(
        "ix_source_file_state_last_seen_snapshot_commit_sha",
        "source_file_state",
        ["last_seen_snapshot_commit_sha"],
    )

    op.create_table(
        "ingestion_run",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("requested_ref", sa.String(length=255), nullable=False),
        sa.Column("snapshot_commit_sha", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("added_count", sa.Integer(), nullable=False),
        sa.Column("modified_count", sa.Integer(), nullable=False),
        sa.Column("deleted_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("indexed_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_ingestion_run_source_id", "ingestion_run", ["source_id"])
    op.create_index(
        "ix_ingestion_run_snapshot_commit_sha",
        "ingestion_run",
        ["snapshot_commit_sha"],
    )
    op.create_index("ix_ingestion_run_status", "ingestion_run", ["status"])

    op.create_table(
        "conversation",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
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
        sa.PrimaryKeyConstraint("conversation_id"),
    )

    op.create_table(
        "answer_interaction",
        sa.Column("interaction_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("abstained", sa.Boolean(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("route_json", sa.JSON(), nullable=True),
        sa.Column("citations_json", sa.JSON(), nullable=True),
        sa.Column("verification_json", sa.JSON(), nullable=True),
        sa.Column("stage_durations_json", sa.JSON(), nullable=True),
        sa.Column("total_duration_seconds", sa.Float(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("interaction_id"),
    )
    op.create_index(
        "ix_answer_interaction_conversation_id",
        "answer_interaction",
        ["conversation_id"],
    )
    op.create_index("ix_answer_interaction_request_id", "answer_interaction", ["request_id"])
    op.create_index("ix_answer_interaction_status", "answer_interaction", ["status"])
    op.create_index("ix_answer_interaction_intent", "answer_interaction", ["intent"])
    op.create_index("ix_answer_interaction_trace_id", "answer_interaction", ["trace_id"])
    op.create_index("ix_answer_interaction_created_at", "answer_interaction", ["created_at"])

    op.create_table(
        "answer_feedback",
        sa.Column("feedback_id", sa.String(length=36), nullable=False),
        sa.Column("interaction_id", sa.String(length=36), nullable=False),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["answer_interaction.interaction_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feedback_id"),
        sa.UniqueConstraint("interaction_id", name="uq_feedback_interaction"),
    )
    op.create_index(
        "ix_answer_feedback_interaction_id",
        "answer_feedback",
        ["interaction_id"],
    )
    op.create_index("ix_answer_feedback_rating", "answer_feedback", ["rating"])

    op.create_table(
        "quality_review",
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("interaction_id", sa.String(length=36), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("root_cause", sa.String(length=32), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["answer_interaction.interaction_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint(
            "interaction_id",
            "trigger",
            name="uq_quality_review_interaction_trigger",
        ),
    )
    op.create_index("ix_quality_review_interaction_id", "quality_review", ["interaction_id"])
    op.create_index("ix_quality_review_trigger", "quality_review", ["trigger"])
    op.create_index("ix_quality_review_status", "quality_review", ["status"])
    op.create_index("ix_quality_review_root_cause", "quality_review", ["root_cause"])
    op.create_index("ix_quality_review_created_at", "quality_review", ["created_at"])

    op.create_table(
        "regression_case",
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("interaction_id", sa.String(length=36), nullable=False),
        sa.Column("benchmark_kind", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_source_ids", sa.JSON(), nullable=False),
        sa.Column("expected_terms", sa.JSON(), nullable=False),
        sa.Column("expected_abstain", sa.Boolean(), nullable=False),
        sa.Column("route_snapshot", sa.JSON(), nullable=True),
        sa.Column("root_cause", sa.String(length=32), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["answer_interaction.interaction_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["quality_review.review_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("case_id"),
        sa.UniqueConstraint("review_id", name="uq_regression_case_review"),
    )
    op.create_index("ix_regression_case_review_id", "regression_case", ["review_id"])
    op.create_index(
        "ix_regression_case_interaction_id",
        "regression_case",
        ["interaction_id"],
    )
    op.create_index(
        "ix_regression_case_benchmark_kind",
        "regression_case",
        ["benchmark_kind"],
    )
    op.create_index("ix_regression_case_root_cause", "regression_case", ["root_cause"])
    op.create_index("ix_regression_case_created_at", "regression_case", ["created_at"])


def downgrade() -> None:
    op.drop_table("regression_case")
    op.drop_table("quality_review")
    op.drop_table("answer_feedback")
    op.drop_table("answer_interaction")
    op.drop_table("conversation")
    op.drop_table("ingestion_run")
    op.drop_table("source_file_state")
    op.drop_table("source_state")
