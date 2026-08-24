from datetime import UTC, datetime

from app.api.routes.conversations import _compact_text, _historical_turn
from app.conversations.store import InteractionRecord


def _record() -> InteractionRecord:
    now = datetime.now(UTC)
    return InteractionRecord(
        interaction_id="22222222-2222-4222-8222-222222222222",
        conversation_id="11111111-1111-4111-8111-111111111111",
        request_id=None,
        question="Can Tractus-X run in the cloud?",
        answer="Yes, it supports cloud-native deployment [S1].",
        status="completed",
        grounded=True,
        abstained=False,
        evidence_count=1,
        model="test-model",
        intent="general",
        route_json={"intent": "general", "source_ids": [], "reasons": []},
        citations_json=[
            {
                "citation_id": "S1",
                "chunk_id": "chunk-1",
                "source_id": "tractusx-docs",
                "repository": "eclipse-tractusx/tractus-x-umbrella",
                "component": "umbrella",
                "version_ref": "main",
                "snapshot_commit_sha": "a" * 40,
                "commit_sha": "b" * 40,
                "path": "README.md",
                "start_line": 10,
                "end_line": 20,
                "source_url": "https://github.com/example/repo/blob/commit/README.md#L10-L20",
                "retrieval_score": 0.8,
                "rerank_score": 0.9,
                "debug_score": None,
                "retrieval_methods": ["dense", "sparse"],
            }
        ],
        verification_json={
            "passed": True,
            "claims": [],
            "unsupported_claim_count": 0,
            "failure_reason": None,
        },
        stage_durations_json=None,
        total_duration_seconds=0.5,
        trace_id=None,
        error_type=None,
        created_at=now,
        feedback_rating=None,
        feedback_reason=None,
        feedback_comment=None,
    )


def test_historical_turn_rehydrates_citations_and_trace_metadata() -> None:
    turn = _historical_turn(_record())

    assert turn is not None
    assert turn.answer.endswith("[S1].")
    assert turn.citations[0].citation_id == "S1"
    assert turn.citations[0].commit_sha == "b" * 40
    assert turn.verification is not None
    assert turn.verification.passed is True
    assert turn.route is not None
    assert turn.route.intent.value == "general"


def test_compact_text_creates_readable_session_titles() -> None:
    assert _compact_text("  How   can I run Tractus-X?  ", limit=72) == "How can I run Tractus-X?"
    assert _compact_text("x" * 100, limit=12) == "xxxxxxxxxxx…"
