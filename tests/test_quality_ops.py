import json
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ops_auth
from app.api.routes import quality_ops
from app.core.config import Settings
from app.quality.store import RegressionRecord, ReviewRecord

_REVIEW_ID = "11111111-1111-4111-8111-111111111111"
_INTERACTION_ID = "22222222-2222-4222-8222-222222222222"
_CASE_ID = "33333333-3333-4333-8333-333333333333"


def _review_record(status: str = "pending") -> ReviewRecord:
    return ReviewRecord(
        review_id=_REVIEW_ID,
        interaction_id=_INTERACTION_ID,
        trigger="feedback_down",
        status=status,
        root_cause=None,
        reviewer_note=None,
        question="How do I create an asset with the SDK?",
        answer="Use create_asset [S1].",
        interaction_status="completed",
        intent="sdk",
        error_type=None,
        feedback_rating="down",
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        reviewed_at=None,
    )


def _regression_record() -> RegressionRecord:
    return RegressionRecord(
        case_id=_CASE_ID,
        review_id=_REVIEW_ID,
        interaction_id=_INTERACTION_ID,
        benchmark_kind="retrieval",
        question="How do I create an asset with the SDK?",
        expected_source_ids=["tractusx-sdk"],
        expected_terms=["create_asset"],
        expected_abstain=False,
        route_snapshot={"intent": "sdk"},
        root_cause="retrieval",
        reviewer_note="Relevant SDK evidence was ranked too low.",
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    )


class FakeQualityStore:
    async def review_counts(self) -> dict[str, int]:
        return {"pending": 2, "promoted": 1}

    async def list_reviews(self, **_kwargs) -> list[ReviewRecord]:
        return [_review_record()]

    async def get_review(self, review_id: str) -> ReviewRecord | None:
        return _review_record() if review_id == _REVIEW_ID else None

    async def dismiss_review(self, **_kwargs) -> ReviewRecord | None:
        return _review_record(status="dismissed")

    async def promote_review(self, **_kwargs) -> RegressionRecord | None:
        return _regression_record()

    async def list_regressions(self, **_kwargs) -> list[RegressionRecord]:
        return [_regression_record()]


def _app() -> FastAPI:
    app = FastAPI()
    app.state.quality_store = FakeQualityStore()
    app.include_router(quality_ops.router)
    return app


def _authorize(monkeypatch) -> None:
    monkeypatch.setattr(
        ops_auth,
        "get_settings",
        lambda: Settings(ops_admin_key="secret"),
    )


def _headers() -> dict[str, str]:
    return {"X-TractusMind-Admin-Key": "secret"}


def test_admin_can_list_pending_quality_reviews(monkeypatch) -> None:
    _authorize(monkeypatch)

    response = TestClient(_app()).get(
        "/v1/ops/quality/reviews?status=pending",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json()[0]["feedback_rating"] == "down"


def test_promote_requires_expected_evidence_for_answerable_case(monkeypatch) -> None:
    _authorize(monkeypatch)

    response = TestClient(_app()).post(
        f"/v1/ops/quality/reviews/{_REVIEW_ID}/decision",
        headers=_headers(),
        json={
            "action": "promote",
            "root_cause": "retrieval",
            "benchmark_kind": "retrieval",
        },
    )

    assert response.status_code == 422


def test_admin_can_promote_review_to_regression_case(monkeypatch) -> None:
    _authorize(monkeypatch)

    response = TestClient(_app()).post(
        f"/v1/ops/quality/reviews/{_REVIEW_ID}/decision",
        headers=_headers(),
        json={
            "action": "promote",
            "root_cause": "retrieval",
            "benchmark_kind": "retrieval",
            "expected_source_ids": ["tractusx-sdk"],
            "expected_terms": ["create_asset"],
            "reviewer_note": "Relevant SDK evidence was ranked too low.",
        },
    )

    assert response.status_code == 200
    assert response.json()["case_id"] == _CASE_ID
    assert response.json()["root_cause"] == "retrieval"


def test_regression_export_matches_retrieval_benchmark_shape(monkeypatch) -> None:
    _authorize(monkeypatch)

    response = TestClient(_app()).get(
        "/v1/ops/quality/regressions/export?benchmark_kind=retrieval",
        headers=_headers(),
    )

    assert response.status_code == 200
    payload = json.loads(response.text.strip())
    assert payload["id"] == _CASE_ID
    assert payload["category"] == "production-retrieval"
    assert payload["expected_sources"] == ["tractusx-sdk"]
    assert payload["expected_terms"] == ["create_asset"]
    assert "answerable" not in payload
