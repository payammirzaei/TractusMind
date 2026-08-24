from app.generation.service import GroundedAnswerService
from app.generation.verification import ClaimVerifier
from app.retrieval.models import RetrievalHit
from app.routing.models import QueryRoute


class FakeRetrieval:
    def __init__(self, hit: RetrievalHit) -> None:
        self.hit = hit

    async def search(
        self,
        query: str,
        *,
        limit: int = 6,
        route: QueryRoute | None = None,
    ) -> list[RetrievalHit]:
        return [self.hit]


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


def _cloud_hit() -> RetrievalHit:
    return RetrievalHit(
        chunk_id="cloud-1",
        score=0.9,
        retrieval_score=0.04,
        rerank_score=0.9,
        text="Tractus-X supports cloud-native deployment on Kubernetes using Helm charts.",
        source_id="tractusx-docs",
        repository="eclipse-tractusx/tractus-x-umbrella",
        component="docs",
        version_ref="main",
        commit_sha="b" * 40,
        path="README.md",
        content_type="documentation",
        language="markdown",
        kind="section",
        start_line=10,
        end_line=20,
        symbol=None,
        parent_symbol=None,
        source_url="https://github.com/eclipse-tractusx/tractus-x-umbrella/blob/main/README.md#L10-L20",
    )


async def test_partially_grounded_answer_is_repaired_and_reverified() -> None:
    llm = FakeLLM(
        (
            '{"answer":"Yes, Tractus-X can run in cloud-native Kubernetes environments [S1]. '
            'It also installs every application automatically [S1].",'
            '"citation_ids":["S1"],"grounded":true}'
        ),
        (
            '{"claims":['
            '{"claim":"Tractus-X can run in cloud-native Kubernetes environments.",'
            '"citation_ids":["S1"],"supported":true,"reason":"Directly supported."},'
            '{"claim":"It installs every application automatically.",'
            '"citation_ids":["S1"],"supported":false,"reason":"The evidence does not say this."}'
            '],"all_supported":false}'
        ),
        (
            '{"answer":"Yes. Tractus-X supports cloud-native deployment on Kubernetes using '
            'Helm charts [S1].","citation_ids":["S1"],"grounded":true}'
        ),
        (
            '{"claims":[{"claim":"Tractus-X supports cloud-native deployment on Kubernetes '
            'using Helm charts.","citation_ids":["S1"],"supported":true,'
            '"reason":"Directly supported."}],"all_supported":true}'
        ),
    )
    service = GroundedAnswerService(
        retrieval=FakeRetrieval(_cloud_hit()),  # type: ignore[arg-type]
        llm=llm,
        verifier=ClaimVerifier(llm),
    )

    answer = await service.answer("Is it possible to deploy Tractus-X in the cloud?")

    assert answer.grounded is True
    assert answer.abstained is False
    assert "Yes." in answer.answer
    assert "every application automatically" not in answer.answer
    assert [citation.citation_id for citation in answer.citations] == ["S1"]
    assert answer.verification is not None
    assert answer.verification.passed is True
