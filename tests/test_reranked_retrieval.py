import pytest

from app.retrieval.models import RetrievalHit
from app.retrieval.reranked import RerankedRetrievalService
from app.routing.models import QueryIntent, QueryRoute


def _hit(chunk_id: str) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        score=0.5,
        text=f"text {chunk_id}",
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        version_ref="main",
        commit_sha="a" * 40,
        path="README.md",
        content_type="documentation",
        language="markdown",
        kind="document_section",
        start_line=1,
        end_line=2,
        source_url="https://example.test/source#L1-L2",
    )


class FakeHybridRetrieval:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, QueryRoute | None]] = []

    async def search_hybrid(
        self,
        query: str,
        *,
        limit: int,
        prefetch_limit: int,
        route: QueryRoute | None = None,
    ):
        self.calls.append((query, limit, prefetch_limit, route))
        return [_hit(f"chunk-{index}") for index in range(limit)]


class FakeReranker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    async def rerank(self, query: str, candidates, *, limit: int):
        self.calls.append((query, len(candidates), limit))
        return list(candidates)[:limit]


@pytest.mark.asyncio
async def test_reranked_retrieval_uses_candidate_budget_and_route() -> None:
    retrieval = FakeHybridRetrieval()
    reranker = FakeReranker()
    service = RerankedRetrievalService(
        retrieval=retrieval,  # type: ignore[arg-type]
        reranker=reranker,  # type: ignore[arg-type]
        candidate_k=20,
        prefetch_k=40,
    )
    route = QueryRoute(
        intent=QueryIntent.SDK,
        source_ids=["tractusx-sdk", "tractusx-docs"],
    )

    hits = await service.search("create asset", limit=5, route=route)

    assert len(hits) == 5
    assert retrieval.calls == [("create asset", 20, 40, route)]
    assert reranker.calls == [("create asset", 20, 5)]
