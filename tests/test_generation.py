from app.generation.context import build_grounded_context
from app.generation.service import GroundedAnswerService
from app.generation.verification import ClaimVerifier
from app.retrieval.models import RetrievalHit
from app.routing.models import QueryRoute


def _hit(
    *,
    score: float = 0.8,
    chunk_id: str = "chunk-1",
    text: str = "The SDK connector service can create an asset with create_asset.",
    path: str = "tractusx_sdk/connector.py",
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        score=score,
        retrieval_score=0.03,
        rerank_score=score,
        text=text,
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        version_ref="main",
        commit_sha="a" * 40,
        path=path,
        content_type="code",
        language="python",
        kind="code_symbol",
        start_line=10,
        end_line=20,
        symbol="create_asset",
        parent_symbol="ConnectorService",
        source_url=f"https://github.com/example/repo/blob/commit/{path}#L10-L20",
    )


class FakeRetrieval:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.last_route: QueryRoute | None = None

    async def search(
        self,
        query: str,
        *,
        limit: int = 6,
        route: QueryRoute | None = None,
    ) -> list[RetrievalHit]:
        self.last_route = route
        return self.hits[:limit]


class FakeLLM:
    model_name = "test-model"

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.responses:
            raise AssertionError("FakeLLM has no response left")
        return self.responses.pop(0)

    async def close(self) -> None:
        return None


def _service(hits: list[RetrievalHit], *responses: str) -> GroundedAnswerService:
    llm = FakeLLM(*responses)
    return GroundedAnswerService(
        retrieval=FakeRetrieval(hits),  # type: ignore[arg-type]
        llm=llm,
        verifier=ClaimVerifier(llm),
    )


def test_context_assigns_backend_owned_citation_ids() -> None:
    context = build_grounded_context([_hit()])

    assert "[S1]" in context.text
    assert context.citations["S1"].commit_sha == "a" * 40
    assert context.citations["S1"].version_ref == "main"
    assert context.citations["S1"].start_line == 10


async def test_grounded_answer_passes_claim_verification() -> None:
    service = _service(
        [_hit()],
        '{"answer":"Use create_asset [S1].","citation_ids":["S1"],"grounded":true}',
        (
            '{"claims":[{"claim":"The SDK supports create_asset.",'
            '"citation_ids":["S1"],"supported":true,"reason":"Directly supported."}],'
            '"all_supported":true}'
        ),
    )

    answer = await service.answer("How do I create an asset with the SDK?")

    assert answer.grounded is True
    assert answer.abstained is False
    assert answer.citations[0].citation_id == "S1"
    assert answer.route is not None
    assert answer.route.intent.value == "sdk"
    assert "tractusx-sdk" in answer.route.source_ids
    assert answer.verification is not None
    assert answer.verification.passed is True


async def test_grounded_answer_ignores_extra_declared_citation_metadata() -> None:
    service = _service(
        [_hit()],
        '{"answer":"Use create_asset [S1].","citation_ids":["S1","S2"],"grounded":true}',
        (
            '{"claims":[{"claim":"Use create_asset.",'
            '"citation_ids":["S1"],"supported":true,"reason":"Directly supported."}],'
            '"all_supported":true}'
        ),
    )

    answer = await service.answer("How do I create an asset with the SDK?")

    assert answer.grounded is True
    assert answer.abstained is False
    assert [citation.citation_id for citation in answer.citations] == ["S1"]


async def test_verifier_ignores_extra_valid_evidence_when_inline_support_exists() -> None:
    service = _service(
        [
            _hit(),
            _hit(
                chunk_id="chunk-2",
                text="The SDK documentation also describes connector asset operations.",
                path="docs/assets.md",
            ),
        ],
        '{"answer":"Use create_asset [S1].","citation_ids":["S1"],"grounded":true}',
        (
            '{"claims":[{"claim":"Use create_asset.",'
            '"citation_ids":["S1","S2"],"supported":true,'
            '"reason":"S1 directly supports the claim; S2 is additional support."}],'
            '"all_supported":true}'
        ),
    )

    answer = await service.answer("How do I create an asset with the SDK?")

    assert answer.grounded is True
    assert answer.abstained is False
    assert answer.verification is not None
    assert answer.verification.passed is True
    assert answer.verification.claims[0].citation_ids == ["S1"]


async def test_answer_abstains_when_claim_is_unsupported() -> None:
    service = _service(
        [_hit()],
        '{"answer":"Assets require OAuth [S1].","citation_ids":["S1"],"grounded":true}',
        (
            '{"claims":[{"claim":"Assets require OAuth.",'
            '"citation_ids":["S1"],"supported":false,"reason":"Evidence does not say this."}],'
            '"all_supported":false}'
        ),
    )

    answer = await service.answer("Question")

    assert answer.grounded is False
    assert answer.abstained is True
    assert answer.route is not None
    assert answer.verification is not None
    assert answer.verification.passed is False
    assert answer.verification.unsupported_claim_count == 1


async def test_answer_abstains_when_llm_invents_citation() -> None:
    service = _service(
        [_hit()],
        '{"answer":"Unsupported claim [S9].","citation_ids":["S9"],"grounded":true}',
    )

    answer = await service.answer("Question")

    assert answer.grounded is False
    assert answer.abstained is True
    assert answer.citations == []


async def test_verifier_rejects_claim_citation_not_present_in_answer() -> None:
    service = _service(
        [_hit()],
        '{"answer":"Use create_asset [S1].","citation_ids":["S1"],"grounded":true}',
        (
            '{"claims":[{"claim":"Use create_asset.",'
            '"citation_ids":["S2"],"supported":true,"reason":"Claimed support."}],'
            '"all_supported":true}'
        ),
    )

    answer = await service.answer("Question")

    assert answer.abstained is True
    assert answer.verification is not None
    assert answer.verification.failure_reason == "claim_citation_validation_failed"


async def test_answer_abstains_before_llm_when_no_evidence() -> None:
    service = _service([], "should not be used")

    answer = await service.answer("Question")

    assert answer.abstained is True
    assert answer.evidence_count == 0
    assert answer.route is not None
