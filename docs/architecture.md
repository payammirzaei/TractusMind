# Architecture

TractusMind is designed as a source-grounded engineering copilot rather than a generic chatbot.
The first production-shaped deployment separates request serving, ingestion work, retrieval
storage, application state, and job orchestration.

```text
Public Internet
      |
      v
 FastAPI API
      |
      +---------------- private network ----------------+
      |                 |             |                 |
      v                 v             v                 v
 Ingestion Worker     Qdrant       PostgreSQL          Redis
                         |
                  Dense + Sparse
                    Retrieval
```

## Responsibilities

- **FastAPI**: query API, health endpoints, orchestration, and later authentication.
- **Worker**: crawling, parsing, code-aware chunking, embeddings, and incremental indexing.
- **Qdrant**: dense/sparse retrieval vectors plus chunk retrieval metadata.
- **PostgreSQL**: source registry, versions/commits, ingestion runs, evaluations,
  conversations, and feedback.
- **Redis**: background job queue, locks, and short-lived cache.
- **S3-compatible storage**: immutable/raw source snapshots and ingestion artifacts.

## Production query path

```text
question
  -> deterministic query router
  -> intent + source/version/ref/commit route
  -> Qdrant payload filter
  -> dense + BM25 retrieval
  -> RRF fusion
  -> cross-encoder reranking
  -> evidence threshold
  -> grounded generation
  -> citation validation
  -> claim verification
  -> final answer or abstention
```

The router currently recognizes SDK, EDC, DTR, semantic-model, release/version, debugging, and
general queries. Source filters are deliberately deterministic so routing decisions can be
inspected and benchmarked without adding another LLM call.

Semantic release versions such as `24.05` are extracted and preserved in the route but are not
used as a hard payload filter because a release repository can document several releases at the
same indexed ref. Explicit `ref:` and `commit:` constraints are hard filters and fail closed when
that indexed provenance is unavailable.

## Provenance contract

Every fetched document and derived chunk carries:

```text
source_id
repository
component
version_ref
commit_sha
path
blob_sha
chunk_id
line range
source URL
```

This contract survives retrieval and is returned in answer citations. Exact commit SHA remains
the immutable source identity; `version_ref` records the human-facing branch or tag that was
resolved to that commit during ingestion.

## Retrieval direction

The retrieval pipeline evolves deliberately:

1. Dense baseline
2. Dense + sparse hybrid retrieval
3. RRF fusion
4. Cross-encoder reranking
5. Version- and metadata-aware routing/filtering
6. Debugging-specific exact-search lane
7. Code-aware and graph-enhanced retrieval only when benchmark results justify it

Every answer should remain traceable to repository/file/version/commit/chunk and retrieval
evidence.
