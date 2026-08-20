import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.api.ops_auth import require_ops_admin, require_ops_operator
from app.observability.metrics import (
    QUALITY_REGRESSION_PROMOTIONS,
    QUALITY_REVIEW_DECISIONS,
)
from app.quality.store import RegressionRecord, ReviewRecord, ReviewStateError

router = APIRouter(
    prefix="/v1/ops/quality",
    tags=["quality"],
    dependencies=[Depends(require_ops_operator)],
)

RootCause = Literal[
    "routing",
    "retrieval",
    "citation",
    "generation",
    "verification",
    "source_data",
    "versioning",
    "other",
]
BenchmarkKind = Literal["retrieval", "debug", "answer"]


class ReviewResponse(BaseModel):
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
    feedback_reason: str | None
    feedback_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ReviewDecision(BaseModel):
    action: Literal["dismiss", "promote"]
    root_cause: RootCause
    reviewer_note: str | None = Field(default=None, max_length=4_000)
    benchmark_kind: BenchmarkKind | None = None
    expected_source_ids: list[str] = Field(default_factory=list, max_length=20)
    expected_terms: list[str] = Field(default_factory=list, max_length=50)
    expected_abstain: bool = False


class RegressionResponse(BaseModel):
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


class QualitySummary(BaseModel):
    review_counts: dict[str, int]
    regression_cases: int


def _review(record: ReviewRecord) -> ReviewResponse:
    return ReviewResponse(**record.__dict__)


def _regression(record: RegressionRecord) -> RegressionResponse:
    return RegressionResponse(**record.__dict__)


def _benchmark_payload(record: RegressionRecord) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": record.case_id,
        "category": f"production-{record.root_cause}",
        "question": record.question,
        "expected_sources": record.expected_source_ids,
        "expected_terms": record.expected_terms,
        "source_interaction_id": record.interaction_id,
    }
    if record.benchmark_kind == "answer":
        payload["answerable"] = not record.expected_abstain
    return payload


@router.get("/summary", response_model=QualitySummary)
async def summary(request: Request) -> QualitySummary:
    return QualitySummary(
        review_counts=await request.app.state.quality_store.review_counts(),
        regression_cases=await request.app.state.quality_store.regression_count(),
    )


@router.get("/reviews", response_model=list[ReviewResponse])
async def reviews(
    request: Request,
    review_status: Annotated[
        Literal["pending", "dismissed", "promoted"] | None,
        Query(alias="status"),
    ] = None,
    root_cause: Annotated[RootCause | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReviewResponse]:
    records = await request.app.state.quality_store.list_reviews(
        status=review_status,
        root_cause=root_cause,
        limit=limit,
    )
    return [_review(record) for record in records]


@router.get("/reviews/{review_id}", response_model=ReviewResponse)
async def review(review_id: UUID, request: Request) -> ReviewResponse:
    record = await request.app.state.quality_store.get_review(str(review_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown quality review")
    return _review(record)


@router.post(
    "/reviews/{review_id}/decision",
    dependencies=[Depends(require_ops_admin)],
)
async def decide_review(
    review_id: UUID,
    payload: ReviewDecision,
    request: Request,
) -> ReviewResponse | RegressionResponse:
    if payload.action == "dismiss":
        try:
            record = await request.app.state.quality_store.dismiss_review(
                review_id=str(review_id),
                root_cause=payload.root_cause,
                reviewer_note=payload.reviewer_note,
            )
        except ReviewStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown quality review")
        QUALITY_REVIEW_DECISIONS.labels(
            action="dismiss",
            root_cause=payload.root_cause,
        ).inc()
        return _review(record)

    if payload.benchmark_kind is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="benchmark_kind is required when promoting a review",
        )
    if payload.benchmark_kind != "answer" and payload.expected_abstain:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only answer benchmarks can encode expected abstention",
        )
    if not payload.expected_abstain and not (
        payload.expected_source_ids or payload.expected_terms
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Promoted answerable cases require expected evidence",
        )

    try:
        case = await request.app.state.quality_store.promote_review(
            review_id=str(review_id),
            root_cause=payload.root_cause,
            reviewer_note=payload.reviewer_note,
            benchmark_kind=payload.benchmark_kind,
            expected_source_ids=payload.expected_source_ids,
            expected_terms=payload.expected_terms,
            expected_abstain=payload.expected_abstain,
        )
    except ReviewStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if case is None:
        raise HTTPException(status_code=404, detail="Unknown quality review")
    QUALITY_REVIEW_DECISIONS.labels(
        action="promote",
        root_cause=payload.root_cause,
    ).inc()
    QUALITY_REGRESSION_PROMOTIONS.labels(
        benchmark_kind=payload.benchmark_kind,
    ).inc()
    return _regression(case)


@router.get("/regressions", response_model=list[RegressionResponse])
async def regressions(
    request: Request,
    benchmark_kind: Annotated[BenchmarkKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> list[RegressionResponse]:
    records = await request.app.state.quality_store.list_regressions(
        benchmark_kind=benchmark_kind,
        limit=limit,
    )
    return [_regression(record) for record in records]


@router.get("/regressions/export", response_class=Response)
async def export_regressions(
    request: Request,
    benchmark_kind: Annotated[BenchmarkKind, Query()],
) -> Response:
    records = await request.app.state.quality_store.list_regressions(
        benchmark_kind=benchmark_kind,
        limit=10_000,
    )
    lines = [json.dumps(_benchmark_payload(record), sort_keys=True) for record in records]
    body = "\n".join(lines)
    if body:
        body += "\n"
    return Response(content=body, media_type="application/x-ndjson")
