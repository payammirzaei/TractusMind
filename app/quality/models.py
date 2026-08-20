from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.state.models import Base


class QualityReview(Base):
    __tablename__ = "quality_review"
    __table_args__ = (
        UniqueConstraint(
            "interaction_id",
            "trigger",
            name="uq_quality_review_interaction_trigger",
        ),
    )

    review_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    interaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("answer_interaction.interaction_id", ondelete="CASCADE"),
        index=True,
    )
    trigger: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    root_cause: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegressionCase(Base):
    __tablename__ = "regression_case"
    __table_args__ = (
        UniqueConstraint("review_id", name="uq_regression_case_review"),
    )

    case_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    review_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("quality_review.review_id", ondelete="CASCADE"),
        index=True,
    )
    interaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("answer_interaction.interaction_id", ondelete="CASCADE"),
        index=True,
    )
    benchmark_kind: Mapped[str] = mapped_column(String(32), index=True)
    question: Mapped[str] = mapped_column(Text)
    expected_source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_abstain: Mapped[bool] = mapped_column(default=False)
    route_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    root_cause: Mapped[str] = mapped_column(String(32), index=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
