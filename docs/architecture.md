# Architecture

TractusMind is designed as a source-grounded engineering copilot rather than a generic chatbot.
The production-shaped deployment separates request serving, scheduled ingestion, ingestion work,
retrieval storage, application state, and job orchestration.

```text
Public Internet
      |
      v
 FastAPI API
      |
      +---------------------- private network ----------------------+
      |                    |             |             |            |
      v                    v             v             v            v
 Scheduler -> Redis -> Ingestion Worker  Qdrant     PostgreSQL    Redis
                         |                  |
                         |             Dense + Sparse
                         |               Retrieval
                         v
                  Incremental Sync
```

## Responsibilities

- **FastAPI**: query API, health endpoints, orchestration, and later authentication.
- **Scheduler**: periodically enqueue all enabled source IDs; it never performs ingestion work.
- **Worker**: source locks, crawling, parsing, code-aware chunking, embeddings, and incremental
  indexing.
- **Qdrant**: dense/sparse vectors, exact debug payload indexes, snapshot metadata, and chunks.
- **PostgreSQL**: source/file state, ingestion runs, evaluations, conversations, and feedback.
- **Redis**: Dramatiq queue, distributed per-source ingestion locks, and short-lived cache.
- **S3-compatible storage**: immutable/raw source snapshots and ingestion artifacts.

## Background ingestion path

```text
scheduler tick
  -> enabled sources from config/sources.toml
  -> Dramatiq messages in Redis
  -> one worker job per source
  -> non-blocking Redis distributed source lock
  -> GitHub manifest discovery
  -> PostgreSQL previous source/file state
  -> blob-SHA delta plan
  -> fetch/chunk/embed only added + modified files
  -> Qdrant upsert/update/delete
  -> commit successful source/file state + ingestion_run
```

The default scheduler interval is six hours and is configurable with
`SOURCE_SYNC_INTERVAL_SECONDS`. Per-source distributed locks prevent simultaneous synchronization
of the same source across worker replicas. The default lock TTL is twelve hours and is configurable
with `SOURCE_SYNC_LOCK_SECONDS`.

The default Compose worker runs one thread because an ingestion task may load dense, sparse, and
reranking models. Horizontal scaling remains possible because the source lock is shared through
Redis.

## Production query path

```text
question
  -> deterministic query router
  -> intent + source/version/ref/commit route
  -> Qdrant payload filter
  -> dense + BM25 retrieval
  -> exact debug lane when applicable
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

Incremental ingestion distinguishes the repository snapshot from the exact content commit:

```text
source_id
repository
component
version_ref
snapshot_commit_sha
commit_sha            # exact content/citation commit
path
blob_sha
chunk_id
line range
source URL
```

An unchanged file does not need to be downloaded or embedded when the repository advances. Its
Qdrant `snapshot_commit_sha` is moved to the new repository snapshot while `commit_sha` and its
commit-pinned citation URL continue to identify the exact immutable content that was originally
fetched. This lets `commit:<sha>` select a complete repository snapshot without weakening exact
citation provenance.

## Retrieval direction

The retrieval pipeline evolves deliberately:

1. Dense baseline
2. Dense + sparse hybrid retrieval
3. RRF fusion
4. Cross-encoder reranking
5. Version- and metadata-aware routing/filtering
6. Debugging-specific exact-search lane
7. Incremental source state + scheduled background synchronization
8. Code-aware and graph-enhanced retrieval only when benchmark results justify it

Every answer should remain traceable to repository/file/version/snapshot/content commit/chunk and
retrieval evidence.
