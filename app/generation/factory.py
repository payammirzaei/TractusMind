from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.embeddings.service import DenseEmbeddingService
from app.embeddings.sparse import SparseEmbeddingService
from app.generation.llm import LLMConfigurationError, OpenAICompatibleLLM
from app.generation.service import GroundedAnswerService
from app.generation.verification import ClaimVerifier
from app.reranking.service import CrossEncoderReranker
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.reranked import RerankedRetrievalService


def create_grounded_answer_service(
    settings: Settings,
    qdrant: AsyncQdrantClient,
) -> GroundedAnswerService:
    if not settings.llm_base_url or not settings.llm_model:
        raise LLMConfigurationError("LLM_BASE_URL and LLM_MODEL must be configured")

    hybrid = HybridRetrievalService(
        qdrant=qdrant,
        collection_name=settings.qdrant_collection,
        dense_embedder=DenseEmbeddingService(
            settings.embedding_model,
            batch_size=settings.embedding_batch_size,
        ),
        sparse_embedder=SparseEmbeddingService(
            settings.sparse_embedding_model,
            batch_size=settings.sparse_embedding_batch_size,
        ),
    )
    retrieval = RerankedRetrievalService(
        retrieval=hybrid,
        reranker=CrossEncoderReranker(
            settings.reranker_model,
            batch_size=settings.reranker_batch_size,
        ),
        candidate_k=settings.retrieval_top_k,
        prefetch_k=settings.hybrid_prefetch_k,
    )
    llm = OpenAICompatibleLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model_name=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    return GroundedAnswerService(
        retrieval=retrieval,
        llm=llm,
        verifier=ClaimVerifier(
            llm,
            max_claims=settings.verification_max_claims,
        ),
        evidence_limit=settings.rerank_top_k,
        context_max_chars=settings.generation_context_max_chars,
        minimum_rerank_score=settings.minimum_relevance_score,
    )
