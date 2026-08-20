import pytest

from app.reranking.service import CrossEncoderReranker
from app.retrieval.models import RetrievalHit


def _hit(chunk_id: str, score: float, text: str) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        score=score,
        text=text,
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        commit_sha="a" * 40,
        path="tractusx_sdk/service.py",
        content_type="code",
        language="python",
        kind="code_symbol",
        start_line=1,
        end_line=2,
        symbol=chunk_id,
        parent_symbol="ConnectorService",
        source_url="https://example.test/source#L1-L2",
    )


@pytest.mark.asyncio
async def test_reranker_reorders_candidates_and_preserves_first_stage_score(monkeypatch) -> None:
    reranker = CrossEncoderReranker("Xenova/ms-marco-MiniLM-L-6-v2")
    candidates = [
        _hit("first", 0.91, "less relevant"),
        _hit("second", 0.72, "more relevant"),
    ]

    monkeypatch.setattr(reranker, "_score", lambda query, documents: [-1.5, 4.2])

    hits = await reranker.rerank("create asset", candidates, limit=2)

    assert [hit.chunk_id for hit in hits] == ["second", "first"]
    assert hits[0].score == 4.2
    assert hits[0].rerank_score == 4.2
    assert hits[0].retrieval_score == 0.72
    assert hits[1].retrieval_score == 0.91


def test_reranker_document_text_contains_code_context() -> None:
    reranker = CrossEncoderReranker("Xenova/ms-marco-MiniLM-L-6-v2")
    hit = _hit("create_asset", 0.8, "def create_asset(): ...")

    text = reranker._document_text(hit)

    assert "Repository: eclipse-tractusx/tractusx-sdk" in text
    assert "Symbol: ConnectorService > create_asset" in text
    assert text.endswith("def create_asset(): ...")
