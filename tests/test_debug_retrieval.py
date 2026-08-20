from app.retrieval.debug import DebugRetrievalService, extract_debug_terms
from app.retrieval.models import RetrievalHit
from app.retrieval.reranked import RerankedRetrievalService
from app.routing.models import QueryIntent, QueryRoute


def _hit(
    chunk_id: str,
    *,
    score: float,
    methods: list[str],
    debug_score: float | None = None,
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        score=score,
        debug_score=debug_score,
        retrieval_methods=methods,
        text="ERR unknown command FLUSHDB in connector configuration",
        source_id="tractusx-edc",
        repository="eclipse-tractusx/tractusx-edc",
        component="edc",
        version_ref="main",
        commit_sha="a" * 40,
        path="edc-extension/src/main/java/ConnectorConfig.java",
        content_type="code",
        language="java",
        kind="code_symbol",
        start_line=10,
        end_line=20,
        symbol="ConnectorConfig",
        source_url="https://example.test/source#L10-L20",
    )


class FakeStore:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.condition_count = 0

    async def debug_search(self, conditions, **kwargs):
        self.condition_count = len(conditions)
        return self.hits


class FakeHybrid:
    def __init__(
        self,
        hybrid_hits: list[RetrievalHit],
        exact_hits: list[RetrievalHit],
    ) -> None:
        self.hybrid_hits = hybrid_hits
        self.store = FakeStore(exact_hits)

    async def search_hybrid(self, query: str, **kwargs):
        return self.hybrid_hits


class FakeReranker:
    async def rerank(self, query: str, candidates, *, limit: int):
        return list(candidates)[:limit]


class FakeDebugLane:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.called = False

    async def search_candidates(self, query: str, **kwargs):
        self.called = True
        return self.hits


def test_debug_term_extraction_keeps_exact_engineering_tokens() -> None:
    terms = extract_debug_terms(
        "EDC failed with IllegalStateException: ERR unknown command `FLUSHDB` "
        "at edc/src/main/ConnectorConfig.java with status 500"
    )

    assert "FLUSHDB" in terms.phrases
    assert "IllegalStateException" in terms.identifiers
    assert "edc/src/main/ConnectorConfig.java" in terms.paths
    assert "500" in terms.codes


async def test_debug_lane_fuses_exact_and_hybrid_provenance() -> None:
    exact = _hit(
        "shared",
        score=4.0,
        debug_score=4.0,
        methods=["exact_symbol"],
    )
    hybrid_shared = _hit("shared", score=0.8, methods=["hybrid"])
    hybrid_other = _hit("semantic", score=0.7, methods=["hybrid"])
    hybrid = FakeHybrid([hybrid_shared, hybrid_other], [exact])
    service = DebugRetrievalService(hybrid)  # type: ignore[arg-type]
    route = QueryRoute(intent=QueryIntent.DEBUG, source_ids=["tractusx-edc"])

    hits = await service.search_candidates(
        "ConnectorConfig failed with error 500",
        route=route,
        limit=10,
        prefetch_limit=20,
    )

    assert hits[0].chunk_id == "shared"
    assert hits[0].debug_score == 4.0
    assert hits[0].retrieval_methods == ["exact_symbol", "hybrid"]
    assert hybrid.store.condition_count > 0


async def test_reranker_uses_debug_lane_only_for_debug_routes() -> None:
    hybrid_hit = _hit("hybrid", score=0.5, methods=["hybrid"])
    debug_hit = _hit("debug", score=0.9, methods=["exact_phrase"])
    hybrid = FakeHybrid([hybrid_hit], [])
    debug = FakeDebugLane([debug_hit])
    service = RerankedRetrievalService(
        retrieval=hybrid,  # type: ignore[arg-type]
        reranker=FakeReranker(),  # type: ignore[arg-type]
        debug_retrieval=debug,  # type: ignore[arg-type]
        candidate_k=1,
        prefetch_k=1,
    )

    hits = await service.search(
        "connector error 500",
        limit=1,
        route=QueryRoute(intent=QueryIntent.DEBUG),
    )

    assert debug.called is True
    assert hits[0].chunk_id == "debug"
