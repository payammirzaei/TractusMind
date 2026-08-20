import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.conversations.history import ConversationTurn
from app.conversations.models import AnswerFeedback, AnswerInteraction, Conversation
from app.generation.models import GroundedAnswer
from app.state.models import Base


class ConversationAccessError(RuntimeError):
    pass


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
class ConversationRecord:
    conversation_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class InteractionRecord:
    interaction_id: str
    conversation_id: str
    request_id: str | None
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
    """Persist answer traces and enforce optional authenticated conversation ownership."""

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
                await connection.execute(
                    text(
                        "ALTER TABLE conversation "
                        "ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(36)"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_conversation_owner_user_id "
                        "ON conversation (owner_user_id)"
                    )
                )
            self._schema_ready = True

    async def assert_conversation_access(
        self,
        *,
        conversation_id: str,
        owner_user_id: str | None,
    ) -> bool:
        await self.ensure_schema()
        async with self.sessions() as session:
            conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            return False
        if conversation.owner_user_id != owner_user_id:
            raise ConversationAccessError("conversation is not available")
        return True

    async def load_history(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
        limit: int,
        max_chars: int,
    ) -> list[ConversationTurn]:
        exists = await self.assert_conversation_access(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
        )
        if not exists:
            return []

        statement = (
            select(AnswerInteraction)
            .where(
                AnswerInteraction.conversation_id == conversation_id,
                AnswerInteraction.status == "completed",
            )
            .order_by(AnswerInteraction.created_at.desc())
            .limit(limit)
        )
        async with self.sessions() as session:
            interactions = (await session.scalars(statement)).all()

        selected: list[ConversationTurn] = []
        used = 0
        for interaction in interactions:
            if not interaction.answer:
                continue
            cost = len(interaction.question) + len(interaction.answer) + 32
            if used + cost > max_chars:
                break
            selected.append(
                ConversationTurn(
                    question=interaction.question,
                    answer=interaction.answer,
                )
            )
            used += cost
        selected.reverse()
        return selected

    async def list_owned_conversations(
        self,
        *,
        owner_user_id: str,
        limit: int = 100,
    ) -> list[ConversationRecord]:
        await self.ensure_schema()
        statement = (
            select(Conversation)
            .where(Conversation.owner_user_id == owner_user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        async with self.sessions() as session:
            conversations = (await session.scalars(statement)).all()
        return [
            ConversationRecord(
                conversation_id=conversation.conversation_id,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            for conversation in conversations
        ]

    async def record_answer(
        self,
        *,
        question: str,
        answer: GroundedAnswer,
        conversation_id: str | None,
        owner_user_id: str | None,
        request_id: str | None,
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
                conversation = Conversation(
                    conversation_id=resolved_conversation_id,
                    owner_user_id=owner_user_id,
                )
                session.add(conversation)
            else:
                self._require_owner(conversation, owner_user_id)
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
                    request_id=request_id,
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
        owner_user_id: str | None,
        request_id: str | None,
        error_type: str,
        stage_durations: dict[str, float],
        total_duration_seconds: float,
        trace_id: str | None,
        model: str | None = None,
        intent: str | None = None,
        route_json: dict[str, object] | None = None,
        citations_json: list[dict[str, object]] | None = None,
        evidence_count: int = 0,
    ) -> InteractionIdentity:
        await self.ensure_schema()
        resolved_conversation_id = conversation_id or str(uuid4())
        interaction_id = str(uuid4())

        async with self.sessions.begin() as session:
            conversation = await session.get(Conversation, resolved_conversation_id)
            if conversation is None:
                session.add(
                    Conversation(
                        conversation_id=resolved_conversation_id,
                        owner_user_id=owner_user_id,
                    )
                )
            else:
                self._require_owner(conversation, owner_user_id)
                conversation.updated_at = datetime.now(UTC)

            session.add(
                AnswerInteraction(
                    interaction_id=interaction_id,
                    conversation_id=resolved_conversation_id,
                    request_id=request_id,
                    question=question,
                    answer=None,
                    status="failed",
                    grounded=False,
                    abstained=False,
                    evidence_count=evidence_count,
                    model=model,
                    intent=intent,
                    route_json=route_json,
                    citations_json=citations_json,
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
        actor_user_id: str | None,
        rating: str,
        reason: str | None,
        comment: str | None,
    ) -> FeedbackRecord | None:
        await self.ensure_schema()
        async with self.sessions.begin() as session:
            interaction = await session.get(AnswerInteraction, interaction_id)
            if interaction is None or interaction.status != "completed":
                return None
            conversation = await session.get(Conversation, interaction.conversation_id)
            if conversation is None:
                return None
            if conversation.owner_user_id is not None:
                self._require_owner(conversation, actor_user_id)

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

    @staticmethod
    def _require_owner(conversation: Conversation, owner_user_id: str | None) -> None:
        if conversation.owner_user_id != owner_user_id:
            raise ConversationAccessError("conversation is not available")

    def _interaction_record(
        self,
        interaction: AnswerInteraction,
        feedback: AnswerFeedback | None,
    ) -> InteractionRecord:
        return InteractionRecord(
            interaction_id=interaction.interaction_id,
            conversation_id=interaction.conversation_id,
            request_id=interaction.request_id,
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
