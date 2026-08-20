from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.state.models import Base


class Conversation(Base):
    __tablename__ = "conversation"

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AnswerInteraction(Base):
    __tablename__ = "answer_interaction"

    interaction_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversation.conversation_id", ondelete="CASCADE"),
        index=True,
    )
    request_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_count: Mapped[int] = mapped_column(default=0)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    route_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    citations_json: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    verification_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    stage_durations_json: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    total_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class AnswerFeedback(Base):
    __tablename__ = "answer_feedback"
    __table_args__ = (UniqueConstraint("interaction_id", name="uq_feedback_interaction"),)

    feedback_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    interaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("answer_interaction.interaction_id", ondelete="CASCADE"),
        index=True,
    )
    rating: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
