from collections.abc import Sequence
from math import ceil

import structlog
from qdrant_client import AsyncQdrantClient

from app.chunking.models import KnowledgeChunk
from app.embeddings.service import DenseEmbeddingService
from app.embeddings.sparse import SparseEmbeddingService
from app.embeddings.text import build_embedding_text, build_sparse_text
from app.retrieval.models import RetrievalHit
from app.retrieval.qdrant_store import QdrantKnowledgeStore, model_scoped_collection_name
from app.routing.filters import build_route_filter
from app.routing.models import QueryRoute

logger = structlog.get_logger()


class HybridRetrievalService:
    def __init__(
        self,
        *,
        qdrant: AsyncQdrantClient,
        collection_name: str,
        dense_embedder: DenseEmbeddingService,
        sparse_embedder: SparseEmbeddingService,
    ) -> None:
        self.dense_embedder = dense_embedder
        self.sparse_embedder = sparse_embedder
        scoped_name = model_scoped_collection_name(
            collection_name,
            dense_embedder.model_name,
            sparse_embedder.model_name,
        )
        self.store = QdrantKnowledgeStore(qdrant, scoped_name)

    async def index(
        self,
        chunks: Sequence[KnowledgeChunk],
        *,
        remove_stale_source_versions: bool = False,
    ) -> int:
        if not chunks:
            return 0

        source_ids = {chunk.source_id for chunk in chunks}
        commit_shas = {chunk.commit_sha for chunk in chunks}
        if remove_stale_source_versions and (len(source_ids) != 1 or len(commit_shas) != 1):
            raise ValueError("Stale-version cleanup requires chunks from one source and one commit")

        await self.store.ensure_collection(self.dense_embedder.dimension, hybrid=True)

        # Keep the source-level sync incremental, but bound embedding/upsert memory and
        # make progress visible. FastEmbed has its own internal batching, however passing
        # a whole repository worth of chunks in one logical call still retains all input
        # texts/vectors until the call completes and makes a stalled model opaque.
        index_batch_size = max(
            1,
            min(self.dense_embedder.batch_size, self.sparse_embedder.batch_size),
        )
        batch_count = ceil(len(chunks) / index_batch_size)
        indexed = 0

        for batch_index, offset in enumerate(
            range(0, len(chunks), index_batch_size),
            start=1,
        ):
            batch = list(chunks[offset : offset + index_batch_size])
            logger.info(
                "index_batch_started",
                batch_index=batch_index,
                batch_count=batch_count,
                batch_chunks=len(batch),
                total_chunks=len(chunks),
                source_ids=sorted({chunk.source_id for chunk in batch}),
            )

            dense_texts = [build_embedding_text(chunk) for chunk in batch]
            dense_vectors = await self.dense_embedder.embed_documents(dense_texts)
            logger.info(
                "index_dense_batch_succeeded",
                batch_index=batch_index,
                batch_count=batch_count,
                vector_count=len(dense_vectors),
            )

            sparse_texts = [build_sparse_text(chunk) for chunk in batch]
            sparse_vectors = await self.sparse_embedder.embed_documents(sparse_texts)
            logger.info(
                "index_sparse_batch_succeeded",
                batch_index=batch_index,
                batch_count=batch_count,
                vector_count=len(sparse_vectors),
            )

            batch_indexed = await self.store.upsert_chunks(
                batch,
                dense_vectors,
                sparse_vectors=sparse_vectors,
                embedding_model=self.dense_embedder.model_name,
                sparse_model=self.sparse_embedder.model_name,
            )
            indexed += batch_indexed
            logger.info(
                "index_batch_succeeded",
                batch_index=batch_index,
                batch_count=batch_count,
                indexed=batch_indexed,
                indexed_total=indexed,
                total_chunks=len(chunks),
            )

        if remove_stale_source_versions:
            await self.store.remove_stale_source_versions(
                source_id=next(iter(source_ids)),
                current_commit_sha=next(iter(commit_shas)),
            )

        return indexed

    async def search_dense(
        self,
        query: str,
        *,
        limit: int = 10,
        route: QueryRoute | None = None,
    ) -> list[RetrievalHit]:
        dense_vector = await self.dense_embedder.embed_query(query)
        return await self.store.dense_search(
            dense_vector,
            limit=limit,
            query_filter=build_route_filter(route),
        )

    async def search_hybrid(
        self,
        query: str,
        *,
        limit: int = 10,
        prefetch_limit: int = 40,
        route: QueryRoute | None = None,
    ) -> list[RetrievalHit]:
        dense_vector = await self.dense_embedder.embed_query(query)
        sparse_vector = await self.sparse_embedder.embed_query(query)
        return await self.store.hybrid_search(
            dense_vector,
            sparse_vector,
            limit=limit,
            prefetch_limit=max(prefetch_limit, limit),
            query_filter=build_route_filter(route),
        )
