import hashlib
import uuid
from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient, models

from app.chunking.models import KnowledgeChunk
from app.retrieval.models import RetrievalHit

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"


def model_scoped_collection_name(
    base_name: str,
    embedding_model: str,
    sparse_model: str | None = None,
) -> str:
    identity = embedding_model if sparse_model is None else f"{embedding_model}|{sparse_model}"
    model_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"{base_name}__{model_hash}"


class QdrantKnowledgeStore:
    def __init__(self, client: AsyncQdrantClient, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name

    async def ensure_collection(self, dimension: int, *, hybrid: bool = False) -> None:
        exists = await self.client.collection_exists(self.collection_name)
        if not exists:
            sparse_config = None
            if hybrid:
                sparse_config = {
                    SPARSE_VECTOR_NAME: models.SparseVectorParams(
                        modifier=models.Modifier.IDF
                    )
                }

            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: models.VectorParams(
                        size=dimension,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config=sparse_config,
            )

        await self._ensure_payload_indexes()

    async def _ensure_payload_indexes(self) -> None:
        collection = await self.client.get_collection(self.collection_name)
        existing = set(collection.payload_schema)

        for field in (
            "source_id",
            "repository",
            "component",
            "version_ref",
            "snapshot_commit_sha",
            "commit_sha",
            "content_type",
            "language",
            "kind",
            "path",
            "symbol",
            "parent_symbol",
        ):
            if field in existing:
                continue
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

        if "debug_text" not in existing:
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="debug_text",
                field_schema=models.TextIndexParams(
                    type=models.TextIndexType.TEXT,
                    tokenizer=models.TokenizerType.WHITESPACE,
                    min_token_len=1,
                    max_token_len=256,
                    lowercase=True,
                    phrase_matching=True,
                ),
                wait=True,
            )

    async def upsert_chunks(
        self,
        chunks: Sequence[KnowledgeChunk],
        dense_vectors: Sequence[Sequence[float]],
        *,
        embedding_model: str,
        sparse_vectors: Sequence[models.SparseVector] | None = None,
        sparse_model: str | None = None,
        batch_size: int = 128,
    ) -> int:
        if len(chunks) != len(dense_vectors):
            raise ValueError("chunks and dense_vectors must have the same length")
        if sparse_vectors is not None and len(chunks) != len(sparse_vectors):
            raise ValueError("chunks and sparse_vectors must have the same length")

        indexed = 0
        for start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[start : start + batch_size]
            batch_dense = dense_vectors[start : start + batch_size]
            batch_sparse = sparse_vectors[start : start + batch_size] if sparse_vectors else None

            points: list[models.PointStruct] = []
            for offset, (chunk, dense_vector) in enumerate(
                zip(batch_chunks, batch_dense, strict=True)
            ):
                vectors: dict[str, object] = {DENSE_VECTOR_NAME: list(dense_vector)}
                if batch_sparse is not None:
                    vectors[SPARSE_VECTOR_NAME] = batch_sparse[offset]

                points.append(
                    models.PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"tractusmind:{chunk.chunk_id}")),
                        vector=vectors,
                        payload=self._payload(chunk, embedding_model, sparse_model),
                    )
                )

            await self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            indexed += len(points)

        return indexed

    async def update_source_snapshot(
        self,
        *,
        source_id: str,
        paths: Sequence[str],
        version_ref: str,
        snapshot_commit_sha: str,
    ) -> None:
        if not paths:
            return
        await self.client.set_payload(
            collection_name=self.collection_name,
            payload={
                "version_ref": version_ref,
                "snapshot_commit_sha": snapshot_commit_sha,
            },
            points=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_id",
                        match=models.MatchValue(value=source_id),
                    ),
                    models.FieldCondition(
                        key="path",
                        match=models.MatchAny(any=list(paths)),
                    ),
                ]
            ),
            wait=True,
        )

    async def delete_source_paths(
        self,
        *,
        source_id: str,
        paths: Sequence[str],
        keep_snapshot_commit_sha: str | None = None,
    ) -> None:
        if not paths:
            return

        must = [
            models.FieldCondition(
                key="source_id",
                match=models.MatchValue(value=source_id),
            ),
            models.FieldCondition(
                key="path",
                match=models.MatchAny(any=list(paths)),
            ),
        ]
        must_not = []
        if keep_snapshot_commit_sha is not None:
            must_not.append(
                models.FieldCondition(
                    key="snapshot_commit_sha",
                    match=models.MatchValue(value=keep_snapshot_commit_sha),
                )
            )

        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=must, must_not=must_not)
            ),
            wait=True,
        )

    async def remove_stale_source_versions(
        self,
        source_id: str,
        current_commit_sha: str,
    ) -> None:
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source_id",
                            match=models.MatchValue(value=source_id),
                        )
                    ],
                    must_not=[
                        models.FieldCondition(
                            key="snapshot_commit_sha",
                            match=models.MatchValue(value=current_commit_sha),
                        )
                    ],
                )
            ),
            wait=True,
        )

    async def dense_search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int = 10,
        query_filter: models.Filter | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievalHit]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=list(query_vector),
            using=DENSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return self._hits(result.points, method="dense")

    async def hybrid_search(
        self,
        dense_vector: Sequence[float],
        sparse_vector: models.SparseVector,
        *,
        limit: int = 10,
        prefetch_limit: int = 40,
        query_filter: models.Filter | None = None,
    ) -> list[RetrievalHit]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=list(dense_vector),
                    using=DENSE_VECTOR_NAME,
                    limit=prefetch_limit,
                ),
                models.Prefetch(
                    query=sparse_vector,
                    using=SPARSE_VECTOR_NAME,
                    limit=prefetch_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return self._hits(result.points, method="hybrid")

    async def debug_search(
        self,
        conditions: Sequence[tuple[models.FieldCondition, float, str]],
        *,
        query_filter: models.Filter | None = None,
        limit: int = 30,
        per_condition_limit: int = 20,
    ) -> list[RetrievalHit]:
        aggregated: dict[str, dict[str, object]] = {}

        for condition, weight, method in conditions:
            points, _ = await self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=self._merge_filter(query_filter, condition),
                limit=per_condition_limit,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                chunk_id = str(payload.get("chunk_id", point.id))
                entry = aggregated.setdefault(
                    chunk_id,
                    {
                        "payload": payload,
                        "score": 0.0,
                        "methods": set(),
                    },
                )
                entry["score"] = float(entry["score"]) + weight
                methods = entry["methods"]
                if isinstance(methods, set):
                    methods.add(method)

        hits = [
            self._hit_from_payload(
                entry["payload"],
                score=float(entry["score"]),
                debug_score=float(entry["score"]),
                methods=sorted(entry["methods"]),
            )
            for entry in aggregated.values()
            if isinstance(entry["payload"], dict)
            and isinstance(entry["methods"], set)
        ]
        hits.sort(
            key=lambda hit: (
                hit.debug_score if hit.debug_score is not None else 0.0,
                hit.chunk_id,
            ),
            reverse=True,
        )
        return hits[:limit]

    def _merge_filter(
        self,
        base: models.Filter | None,
        condition: models.FieldCondition,
    ) -> models.Filter:
        if base is None:
            return models.Filter(must=[condition])
        return models.Filter(must=[base, condition])

    def _hits(
        self,
        points: Sequence[object],
        *,
        method: str,
    ) -> list[RetrievalHit]:
        hits: list[RetrievalHit] = []
        for point in points:
            payload = point.payload or {}  # type: ignore[attr-defined]
            hits.append(
                self._hit_from_payload(
                    payload,
                    score=float(point.score),  # type: ignore[attr-defined]
                    methods=[method],
                )
            )
        return hits

    def _hit_from_payload(
        self,
        payload: dict[str, object],
        *,
        score: float,
        debug_score: float | None = None,
        methods: list[str] | None = None,
    ) -> RetrievalHit:
        return RetrievalHit(
            chunk_id=str(payload["chunk_id"]),
            score=score,
            debug_score=debug_score,
            retrieval_methods=methods or [],
            text=str(payload["text"]),
            source_id=str(payload["source_id"]),
            repository=str(payload["repository"]),
            component=str(payload["component"]),
            version_ref=(
                str(payload["version_ref"]) if payload.get("version_ref") else None
            ),
            snapshot_commit_sha=(
                str(payload["snapshot_commit_sha"])
                if payload.get("snapshot_commit_sha")
                else None
            ),
            commit_sha=str(payload["commit_sha"]),
            path=str(payload["path"]),
            content_type=str(payload["content_type"]),
            language=(str(payload["language"]) if payload.get("language") else None),
            kind=str(payload["kind"]),
            start_line=int(payload["start_line"]),
            end_line=int(payload["end_line"]),
            symbol=(str(payload["symbol"]) if payload.get("symbol") else None),
            parent_symbol=(
                str(payload["parent_symbol"]) if payload.get("parent_symbol") else None
            ),
            section_path=[str(item) for item in payload.get("section_path", [])],
            source_url=str(payload["line_source_url"]),
        )

    def _payload(
        self,
        chunk: KnowledgeChunk,
        embedding_model: str,
        sparse_model: str | None = None,
    ) -> dict[str, object]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "source_id": chunk.source_id,
            "repository": chunk.repository,
            "component": chunk.component,
            "version_ref": chunk.version_ref,
            "snapshot_commit_sha": chunk.commit_sha,
            "commit_sha": chunk.commit_sha,
            "path": chunk.path,
            "blob_sha": chunk.blob_sha,
            "content_type": chunk.content_type,
            "language": chunk.language,
            "kind": chunk.kind.value,
            "text": chunk.text,
            "debug_text": self._debug_text(chunk),
            "text_sha256": chunk.text_sha256,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "symbol": chunk.symbol,
            "parent_symbol": chunk.parent_symbol,
            "section_path": chunk.section_path,
            "part": chunk.part,
            "source_url": chunk.source_url,
            "line_source_url": chunk.line_source_url,
            "embedding_model": embedding_model,
            "sparse_model": sparse_model,
        }

    def _debug_text(self, chunk: KnowledgeChunk) -> str:
        values = [chunk.path]
        if chunk.parent_symbol:
            values.append(chunk.parent_symbol)
        if chunk.symbol:
            values.append(chunk.symbol)
        values.extend(chunk.section_path)
        values.append(chunk.text)
        return "\n".join(values)
