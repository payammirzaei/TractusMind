from app.evaluation.benchmark import BenchmarkCase, aggregate_metrics, evaluate_case, is_relevant
from app.retrieval.models import RetrievalHit


def _hit(*, source_id: str, text: str, symbol: str | None = None) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=f"chunk-{source_id}-{symbol or 'text'}",
        score=0.9,
        text=text,
        source_id=source_id,
        repository=f"eclipse-tractusx/{source_id}",
        component="test",
        commit_sha="a" * 40,
        path="README.md",
        content_type="documentation",
        language="markdown",
        kind="document_section",
        start_line=1,
        end_line=5,
        symbol=symbol,
        source_url="https://github.com/eclipse-tractusx/test#L1-L5",
    )


def test_relevance_requires_source_and_expected_terms() -> None:
    case = BenchmarkCase(
        id="asset",
        category="coding",
        question="How do I create an asset?",
        expected_sources=("tractusx-sdk",),
        expected_terms=("create_asset",),
    )

    assert is_relevant(case, _hit(source_id="tractusx-sdk", text="x", symbol="create_asset"))
    assert not is_relevant(case, _hit(source_id="tractusx-edc", text="create_asset"))
    assert not is_relevant(case, _hit(source_id="tractusx-sdk", text="unrelated"))


def test_metrics_reward_earlier_relevant_results() -> None:
    case = BenchmarkCase(
        id="edc",
        category="concept",
        question="control plane vs data plane",
        expected_sources=("tractusx-edc",),
        expected_terms=("control", "data"),
    )
    hits = [
        _hit(source_id="tractusx-sdk", text="unrelated"),
        _hit(source_id="tractusx-edc", text="Control plane and Data plane"),
    ]

    recall, reciprocal_rank, ndcg = evaluate_case(case, hits, k=2)

    assert recall == 1
    assert reciprocal_rank == 0.5
    assert 0 < ndcg <= 1

    aggregate = aggregate_metrics([(recall, reciprocal_rank, ndcg)])
    assert aggregate.recall_at_k == 1.0
    assert aggregate.mrr == 0.5
