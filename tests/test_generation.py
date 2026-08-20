from app.generation.context import build_grounded_context
from app.generation.service import GroundedAnswerService
from app.generation.verification import ClaimVerifier
from app.retrieval.models import RetrievalHit


def _hit(*, score: float = 0.8) -> RetrievalHit:
    return RetrievalHit(
        chunk_id="chunk-1",
        score=score,
        retrieval_score=0.03,
        rerank_score=score,
        text="The SDK connector service can create an asset with create_asset.",
        source_id="tractusx-sdk",
        repository="eclipse-tractusx/tractusx-sdk",
        component="sdk",
        commit_sha="a" * 40,
        path="tractusx_sdk/connector.py",
        content_type="code",
        language="python",
        kind="code_symbol",
        start_line=10,
        end_line=20,
        symbol="create_asset",
        parent_symbol="ConnectorService",
        source_url="https://github.com/example/repo/blob/commit/file.py#L10-L20",
    )


class FakeRetrieval:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits

    async def search(self, query: str, *, limit: int = 6) -> list[RetrievalHit]:
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

    answer = await service.answer("How do I create an asset?")

    assert answer.grounded is True
    assert answer.abstained is False
    assert answer.citations[0].citation_id == "S1"
    assert answer.verification is not None
    assert answer.verification.passed is True


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
