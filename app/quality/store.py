import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.conversations.models import AnswerFeedback, AnswerInteraction
from app.quality.models import QualityReview, RegressionCase
from app.state.models import Base


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    interaction_id: str
    trigger: str
    status: str
    root_cause: str | None
    reviewer_note: str | None
    question: str
    answer: str | None
    interaction_status: str
    intent: str | None
    error_type: str | None
    feedback_rating: str | None
    created_at: datetime
    reviewed_at: datetime | None


@dataclass(frozen=True)
class RegressionRecord:
    case_id: str
    review_id: str
    interaction_id: str
    benchmark_kind: str
    question: str
    expected_source_ids: list[str]
    expected_terms: list[str]
    expected_abstain: bool
    route_snapshot: dict[str, object] | None
    root_cause: str
    reviewer_note: str | None
    created_at: datetime


class QualityStore:
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

    async def ensure_review(self, *, interaction_id: str, trigger: str) -> str | None:
        await self.ensure_schema()
        async with self.sessions.begin() as session:
            interaction = await session.get(AnswerInteraction, interaction_id)
            if interaction is None:
                return None
            existing = await session.scalar(
                select(QualityReview).where(
                    QualityReview.interaction_id == interaction_id,
                    QualityReview.trigger == trigger,
                )
            )
            if existing is not None:
                return existing.review_id
            review = QualityReview(interaction_id=interaction_id, trigger=trigger)
            session.add(review)
            await session.flush()
            return review.review_id

    def _review_statement(self):
        return (
            select(QualityReview, AnswerInteraction, AnswerFeedback)
            .join(
                AnswerInteraction,
                AnswerInteraction.interaction_id == QualityReview.interaction_id,
            )
            .outerjoin(
                AnswerFeedback,
                AnswerFeedback.interaction_id == AnswerInteraction.interaction_id,
            )
        )

    async def list_reviews(
        self,
        *,
        status: str | None = None,
        root_cause: str | None = None,
        limit: int = 50,
    ) -> list[ReviewRecord]:
        await self.ensure_schema()
        statement = self._review_statement().order_by(QualityReview.created_at.desc()).limit(limit)
        if status is not None:
            statement = statement.where(QualityReview.status == status)
        if root_cause is not None:
            statement = statement.where(QualityReview.root_cause == root_cause)
        async with self.sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            self._review_record(review, interaction, feedback)
            for review, interaction, feedback in rows
        ]

    async def get_review(self, review_id: str) -> ReviewRecord | None:
        await self.ensure_schema()
        statement = self._review_statement().where(QualityReview.review_id == review_id)
        async with self.sessions() as session:
            row = (await session.execute(statement)).first()
        if row is None:
            return None
        review, interaction, feedback = row
        return self._review_record(review, interaction, feedback)

    async def dismiss_review(
        self,
        *,
        review_id: str,
        root_cause: str,
        reviewer_note: str | None,
    ) -> ReviewRecord | None:
        await self.ensure_schema()
        async with self.sessions.begin() as session:
            review = await session.get(QualityReview, review_id)
            if review is None:
                return None
            review.status = "dismissed"
            review.root_cause = root_cause
            review.reviewer_note = reviewer_note
            review.reviewed_at = datetime.now(UTC)
        return await self.get_review(review_id)

    async def promote_review(
        self,
        *,
        review_id: str,
        root_cause: str,
        reviewer_note: str | None,
        benchmark_kind: str,
        expected_source_ids: list[str],
        expected_terms: list[str],
        expected_abstain: bool,
    ) -> RegressionRecord | None:
        await self.ensure_schema()
        async with self.sessions.begin() as session:
            review = await session.get(QualityReview, review_id)
            if review is None:
                return None
            interaction = await session.get(AnswerInteraction, review.interaction_id)
            if interaction is None:
                return None
            existing = await session.scalar(
                select(RegressionCase).where(RegressionCase.review_id == review_id)
            )
            if existing is not None:
                return self._regression_record(existing)

            case = RegressionCase(
                review_id=review.review_id,
                interaction_id=interaction.interaction_id,
                benchmark_kind=benchmark_kind,
                question=interaction.question,
                expected_source_ids=expected_source_ids,
                expected_terms=expected_terms,
                expected_abstain=expected_abstain,
                route_snapshot=interaction.route_json,
                root_cause=root_cause,
                reviewer_note=reviewer_note,
            )
            session.add(case)
            review.status = "promoted"
            review.root_cause = root_cause
            review.reviewer_note = reviewer_note
            review.reviewed_at = datetime.now(UTC)
            await session.flush()
            return self._regression_record(case)

    async def list_regressions(
        self,
        *,
        benchmark_kind: str | None = None,
        limit: int = 200,
    ) -> list[RegressionRecord]:
        await self.ensure_schema()
        statement = select(RegressionCase).order_by(RegressionCase.created_at.desc()).limit(limit)
        if benchmark_kind is not None:
            statement = statement.where(RegressionCase.benchmark_kind == benchmark_kind)
        async with self.sessions() as session:
            cases = (await session.scalars(statement)).all()
        return [self._regression_record(case) for case in cases]

    async def review_counts(self) -> dict[str, int]:
        await self.ensure_schema()
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(QualityReview.status, func.count()).group_by(QualityReview.status)
                )
            ).all()
        return {str(status): int(count) for status, count in rows}

    def _review_record(
        self,
        review: QualityReview,
        interaction: AnswerInteraction,
        feedback: AnswerFeedback | None,
    ) -> ReviewRecord:
        return ReviewRecord(
            review_id=review.review_id,
            interaction_id=review.interaction_id,
            trigger=review.trigger,
            status=review.status,
            root_cause=review.root_cause,
            reviewer_note=review.reviewer_note,
            question=interaction.question,
            answer=interaction.answer,
            interaction_status=interaction.status,
            intent=interaction.intent,
            error_type=interaction.error_type,
            feedback_rating=feedback.rating if feedback else None,
            created_at=review.created_at,
            reviewed_at=review.reviewed_at,
        )

    def _regression_record(self, case: RegressionCase) -> RegressionRecord:
        return RegressionRecord(
            case_id=case.case_id,
            review_id=case.review_id,
            interaction_id=case.interaction_id,
            benchmark_kind=case.benchmark_kind,
            question=case.question,
            expected_source_ids=list(case.expected_source_ids or []),
            expected_terms=list(case.expected_terms or []),
            expected_abstain=case.expected_abstain,
            route_snapshot=case.route_snapshot,
            root_cause=case.root_cause,
            reviewer_note=case.reviewer_note,
            created_at=case.created_at,
        )
