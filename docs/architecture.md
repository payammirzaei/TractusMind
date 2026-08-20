# Architecture

TractusMind is designed as a source-grounded engineering copilot rather than a generic chatbot.
The production-shaped deployment separates request serving, scheduled ingestion, ingestion work,
retrieval storage, application state, job orchestration, metrics, traces, and interaction history.

```text
Public Internet
      |
      v
 FastAPI API --------------------> OTLP Collector (optional)
      |                                  |
      |                                  v
      |                             Trace backend
      |
      +---------------------- private network ----------------------+
      |                    |             |             |            |
      v                    v             v             v            v
 Scheduler -> Redis -> Ingestion Worker  Qdrant     PostgreSQL    Redis
    |                    |                  |           |
    |                    |             Dense + Sparse  +-- source/file state
    |                    |               Retrieval     +-- ingestion runs
    |                    v                             +-- answer interactions
    |             Incremental Sync                    +-- feedback
    |                                                +-- quality reviews
    |                                                +-- regression cases
    +--------- metrics --+---------> Prometheus
              API metrics ---------> Prometheus
              Dramatiq metrics ----> Prometheus
```

## Responsibilities

- **FastAPI**: grounded query API, feedback API, health endpoints, protected operations API,
  request correlation, Prometheus API metrics, and optional OpenTelemetry tracing.
- **Scheduler**: periodically enqueue all enabled source IDs; it never performs ingestion work.
- **Worker**: source locks, crawling, parsing, code-aware chunking, embeddings, incremental indexing,
  and worker/model metrics.
- **Qdrant**: dense/sparse vectors, exact debug payload indexes, snapshot metadata, and chunks.
- **PostgreSQL**: source/file state, ingestion runs, evaluations, conversations, answer traces,
  citations/verification snapshots, feedback, quality reviews, and reviewed regression cases.
- **Redis**: Dramatiq queue, distributed per-source ingestion locks, and short-lived cache.
- **Prometheus**: API, RAG-stage, local-model, ingestion, scheduler, and native Dramatiq metrics.
- **OpenTelemetry**: optional API/request and RAG-stage traces exported over OTLP/HTTP.
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
  -> persist interaction + citations + verification + timing trace
  -> optional up/down feedback
```

The router currently recognizes SDK, EDC, DTR, semantic-model, release/version, debugging, and
general queries. Source filters are deliberately deterministic so routing decisions can be
inspected and benchmarked without adding another LLM call.

Semantic release versions such as `24.05` are extracted and preserved in the route but are not
used as a hard payload filter because a release repository can document several releases at the
same indexed ref. Explicit `ref:` and `commit:` constraints are hard filters and fail closed when
that indexed provenance is unavailable.

## Conversation and trace persistence

`conversation` groups related requests by an opaque UUID. `answer_interaction` stores an immutable
snapshot of a completed or failed answer request, including route, citations, verification result,
model, grounded/abstained outcome, request-local stage durations, total duration, and OpenTelemetry
trace ID when available.

The request-local timing collector is backed by `contextvars`, so concurrent API requests do not
share stage data. Prometheus remains the aggregate metric system; PostgreSQL stores the trace
snapshot needed to inspect one specific production answer.

Conversation persistence does not automatically add previous turns to the LLM prompt. History
selection is a separate retrieval/context-budget decision and will only be enabled with an explicit
policy.

`answer_feedback` stores one mutable `up` or `down` record per completed interaction. Re-submission
updates the same record. Public conversation-history reads are intentionally absent until user
authentication and ownership checks exist; protected ops endpoints can inspect interactions.

See [`conversation-feedback.md`](conversation-feedback.md).

## Feedback-driven quality loop

Production failures and negative feedback feed a human-reviewed quality path:

```text
failed interaction ---------+
                            +-> quality_review (pending)
down-voted interaction -----+          |
                                       v
                             human root-cause review
                              /                 \
                         dismiss              promote
                                                |
                                                v
                                      regression_case
                                                |
                                                v
                                      benchmark NDJSON export
                                                |
                                                v
                                       repository code review
```

Capture is concurrency-safe and idempotent per interaction/trigger. Raw feedback never becomes a
gold benchmark automatically. Promotion requires an administrator to classify the root cause and
provide expected evidence or expected abstention. Final review decisions cannot be changed into a
contradictory state.

Promoted cases retain their production interaction ID and route snapshot. Benchmark export is
split by benchmark kind so retrieval/debug rows and answer-evaluation rows remain compatible with
the existing loaders.

See [`quality-loop.md`](quality-loop.md).

## Observability contract

Prometheus metrics and OpenTelemetry traces observe the same production paths rather than a second
instrumentation-only implementation.

API metrics use FastAPI route templates instead of raw paths. Pipeline metrics use bounded labels
such as stage and query intent. Ingestion metrics may use source IDs because source IDs come from
the finite allowlisted registry. Arbitrary question text, source code, error bodies, paths, commit
SHAs, chunk IDs, request IDs, trace IDs, credentials, and authorization headers are never metric
labels.

The local Compose topology scrapes:

```text
api:8000/metrics       -> HTTP + RAG pipeline metrics
worker:9101/metrics    -> TractusMind worker/ingestion/model metrics
worker:9191/           -> native Dramatiq queue/runtime metrics
scheduler:9102/metrics -> scheduler enqueue metrics
```

OpenTelemetry export is optional. When `OTEL_TRACES_ENDPOINT` is configured, FastAPI creates the
request/server span and TractusMind adds child spans for retrieval, generation, and verification.
Without an endpoint there is no OTLP exporter dependency at runtime.

Each normal API response receives an `X-Request-ID`. The request ID is also bound to structured
logs; when an OpenTelemetry span is active its trace ID is bound as well. These correlation IDs are
kept out of metric labels.

See [`observability.md`](observability.md) for metric families, security rules, and example PromQL.

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
8. Production observability and measured quality calibration
9. Persisted conversations, answer traces, and user feedback
10. Human-reviewed feedback/failure promotion into regression benchmarks
11. Code-aware and graph-enhanced retrieval only when benchmark results justify it

Every answer should remain traceable to repository/file/version/snapshot/content commit/chunk,
retrieval evidence, verification result, persisted interaction, optional feedback, and any reviewed
regression case derived from it.
