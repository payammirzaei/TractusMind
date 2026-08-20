from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.embeddings.service import DenseEmbeddingService
from app.embeddings.sparse import SparseEmbeddingService
from app.reranking.service import CrossEncoderReranker
from app.retrieval.debug import DebugRetrievalService
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.reranked import RerankedRetrievalService


def create_hybrid_retrieval_service(
    settings: Settings,
    qdrant: AsyncQdrantClient,
) -> HybridRetrievalService:
    return HybridRetrievalService(
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


def create_reranked_retrieval_service(
    settings: Settings,
    qdrant: AsyncQdrantClient,
) -> RerankedRetrievalService:
    hybrid = create_hybrid_retrieval_service(settings, qdrant)
    debug = DebugRetrievalService(
        hybrid,
        exact_k=settings.debug_exact_k,
        rrf_k=settings.debug_rrf_k,
        exact_weight=settings.debug_exact_weight,
        hybrid_weight=settings.debug_hybrid_weight,
    )
    return RerankedRetrievalService(
        retrieval=hybrid,
        reranker=CrossEncoderReranker(
            settings.reranker_model,
            batch_size=settings.reranker_batch_size,
        ),
        debug_retrieval=debug,
        candidate_k=settings.retrieval_top_k,
        prefetch_k=max(
            settings.hybrid_prefetch_k,
            settings.retrieval_top_k,
        ),
    )
