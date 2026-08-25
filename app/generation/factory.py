from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.generation.llm import LLMConfigurationError, OpenAICompatibleLLM
from app.generation.service import GroundedAnswerService
from app.generation.verification import ClaimVerifier
from app.retrieval.factory import create_reranked_retrieval_service


def create_grounded_answer_service(
    settings: Settings,
    qdrant: AsyncQdrantClient,
) -> GroundedAnswerService:
    if not settings.llm_base_url or not settings.llm_model:
        raise LLMConfigurationError(
            "LLM_BASE_URL and LLM_MODEL must be configured"
        )

    retrieval = create_reranked_retrieval_service(settings, qdrant)
    llm = OpenAICompatibleLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model_name=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        max_attempts=settings.llm_max_attempts,
        retry_base_seconds=settings.provider_retry_base_seconds,
        retry_max_seconds=settings.provider_retry_max_seconds,
        circuit_failure_threshold=settings.provider_circuit_failure_threshold,
        circuit_cooldown_seconds=settings.provider_circuit_cooldown_seconds,
        json_mode=True,
    )
    verifier = ClaimVerifier(
        llm,
        max_claims=settings.verification_max_claims,
    )
    return GroundedAnswerService(
        retrieval=retrieval,
        llm=llm,
        verifier=verifier,
        evidence_limit=settings.rerank_top_k,
        context_max_chars=settings.generation_context_max_chars,
        minimum_rerank_score=settings.minimum_relevance_score,
    )
