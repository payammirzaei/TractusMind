import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.conversations.models import AnswerFeedback, AnswerInteraction, Conversation
from app.generation.models import GroundedAnswer
from app.state.models import Base


@dataclass(frozen=True)
class InteractionIdentity:
    interaction_id: str
    conversation_id: str


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    interaction_id: str
    rating: str
    reason: str | None
    comment: str | None


@dataclass(frozen=True)
class InteractionRecord:
    interaction_id: str
    conversation_id: str
    question: str
    answer: str | None
    status: str
    grounded: bool
    abstained: bool
    evidence_count: int
    model: str | None
    intent: str | None
    route_json: dict[str, object] | None
    citations_json: list[dict[str, object]] | None
    verification_json: dict[str, object] | None
    stage_durations_json: dict[str, float] | None
    total_duration_seconds: float | None
    trace_id: str | None
    error_type: str | None
    created_at: datetime
    feedback_rating: str | None
    feedback_reason: str | None
    feedback_comment: str | None


class ConversationStore:
    """Persist answer traces and one mutable feedback record per interaction."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            self._schema_ready = True

    async def record_answer(
        self,
        *,
        question: str,
        answer: GroundedAnswer,
        conversation_id: str | None,
        stage_durations: dict[str, float],
        total_duration_seconds: float,
        trace_id: str | None,
    ) -> InteractionIdentity:
        await self.ensure_schema()
        resolved_conversation_id = conversation_id or str(uuid4())
        interaction_id = str(uuid4())

        async with self.sessions.begin() as session:
            conversation = await session.get(Conversation, resolved_conversation_id)
            if conversation is None:
                conversation = Conversation(conversation_id=resolved_conversation_id)
                session.add(conversation)
            else:
                conversation.updated_at = datetime.now(UTC)

            route_json = answer.route.model_dump(mode="json") if answer.route else None
            verification_json = (
                answer.verification.model_dump(mode="json")
                if answer.verification is not None
                else None
            )
            session.add(
                AnswerInteraction(
                    interaction_id=interaction_id,
                    conversation_id=resolved_conversation_id,
                    question=question,
                    answer=answer.answer,
                    status="completed",
                    grounded=answer.grounded,
                    abstained=answer.abstained,
                    evidence_count=answer.evidence_count,
                    model=answer.model,
                    intent=answer.route.intent.value if answer.route else None,
                    route_json=route_json,
                    citations_json=[
                        citation.model_dump(mode="json") for citation in answer.citations
                    ],
                    verification_json=verification_json,
                    stage_durations_json=stage_durations,
                    total_duration_seconds=total_duration_seconds,
                    trace_id=trace_id,
                )
            )

        return InteractionIdentity(
            interaction_id=interaction_id,
            conversation_id=resolved_conversation_id,
        )

    async def record_failure(
        self,
        *,
        question: str,
        conversation_id: str | None,
        error_type: str,
        stage_durations: dict[str, float],
        total_duration_seconds: float,
        trace_id: str | None,
    ) -> InteractionIdentity:
        await self.ensure_schema()
        resolved_conversation_id = conversation_id or str(uuid4())
        interaction_id = str(uuid4())

        async with self.sessions.begin() as session:
            conversation = await session.get(Conversation, resolved_conversation_id)
            if conversation is None:
                session.add(Conversation(conversation_id=resolved_conversation_id))
            else:
                conversation.updated_at = datetime.now(UTC)

            session.add(
                AnswerInteraction(
                    interaction_id=interaction_id,
                    conversation_id=resolved_conversation_id,
                    question=question,
                    answer=None,
                    status="failed",
                    grounded=False,
                    abstained=False,
                    evidence_count=0,
                    stage_durations_json=stage_durations,
                    total_duration_seconds=total_duration_seconds,
                    trace_id=trace_id,
                    error_type=error_type,
                )
            )

        return InteractionIdentity(
            interaction_id=interaction_id,
            conversation_id=resolved_conversation_id,
        )

    async def upsert_feedback(
        self,
        *,
        interaction_id: str,
        rating: str,
        reason: str | None,
        comment: str | None,
    ) -> FeedbackRecord | None:
        await self.ensure_schema()
        async with self.sessions.begin() as session:
            interaction = await session.get(AnswerInteraction, interaction_id)
            if interaction is None or interaction.status != "completed":
                return None

            feedback = await session.scalar(
                select(AnswerFeedback).where(
                    AnswerFeedback.interaction_id == interaction_id
                )
            )
            if feedback is None:
                feedback = AnswerFeedback(
                    interaction_id=interaction_id,
                    rating=rating,
                    reason=reason,
                    comment=comment,
                )
                session.add(feedback)
                await session.flush()
            else:
                feedback.rating = rating
                feedback.reason = reason
                feedback.comment = comment
                feedback.updated_at = datetime.now(UTC)

            return FeedbackRecord(
                feedback_id=feedback.feedback_id,
                interaction_id=feedback.interaction_id,
                rating=feedback.rating,
                reason=feedback.reason,
                comment=feedback.comment,
            )

    async def list_interactions(
        self,
        *,
        conversation_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[InteractionRecord]:
        await self.ensure_schema()
        statement = (
            select(AnswerInteraction, AnswerFeedback)
            .outerjoin(
                AnswerFeedback,
                AnswerFeedback.interaction_id == AnswerInteraction.interaction_id,
            )
            .order_by(AnswerInteraction.created_at.desc())
            .limit(limit)
        )
        if conversation_id is not None:
            statement = statement.where(
                AnswerInteraction.conversation_id == conversation_id
            )
        if status is not None:
            statement = statement.where(AnswerInteraction.status == status)

        async with self.sessions() as session:
            rows = (await session.execute(statement)).all()

        return [self._interaction_record(interaction, feedback) for interaction, feedback in rows]

    async def get_interaction(self, interaction_id: str) -> InteractionRecord | None:
        await self.ensure_schema()
        statement = (
            select(AnswerInteraction, AnswerFeedback)
            .outerjoin(
                AnswerFeedback,
                AnswerFeedback.interaction_id == AnswerInteraction.interaction_id,
            )
            .where(AnswerInteraction.interaction_id == interaction_id)
        )
        async with self.sessions() as session:
            row = (await session.execute(statement)).first()
        if row is None:
            return None
        interaction, feedback = row
        return self._interaction_record(interaction, feedback)

    async def feedback_counts(self) -> dict[str, int]:
        await self.ensure_schema()
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(AnswerFeedback.rating, func.count())
                    .group_by(AnswerFeedback.rating)
                    .order_by(AnswerFeedback.rating)
                )
            ).all()
        return {str(rating): int(count) for rating, count in rows}

    def _interaction_record(
        self,
        interaction: AnswerInteraction,
        feedback: AnswerFeedback | None,
    ) -> InteractionRecord:
        return InteractionRecord(
            interaction_id=interaction.interaction_id,
            conversation_id=interaction.conversation_id,
            question=interaction.question,
            answer=interaction.answer,
            status=interaction.status,
            grounded=interaction.grounded,
            abstained=interaction.abstained,
            evidence_count=interaction.evidence_count,
            model=interaction.model,
            intent=interaction.intent,
            route_json=interaction.route_json,
            citations_json=interaction.citations_json,
            verification_json=interaction.verification_json,
            stage_durations_json=interaction.stage_durations_json,
            total_duration_seconds=interaction.total_duration_seconds,
            trace_id=interaction.trace_id,
            error_type=interaction.error_type,
            created_at=interaction.created_at,
            feedback_rating=feedback.rating if feedback else None,
            feedback_reason=feedback.reason if feedback else None,
            feedback_comment=feedback.comment if feedback else None,
        )
