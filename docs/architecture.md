# Architecture

TractusMind is designed as a source-grounded engineering copilot rather than a generic chatbot.
The production-shaped deployment separates request serving, identity, scheduled ingestion,
ingestion work, retrieval storage, application state, job orchestration, metrics, traces, and
interaction history.

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
    |                    |             Dense + Sparse  +-- users / hashed API keys
    |                    |               Retrieval     +-- source/file state
    |                    v                             +-- ingestion runs
    |             Incremental Sync                    +-- owned conversations
    |                                                +-- answer interactions
    |                                                +-- feedback
    |                                                +-- quality reviews
    |                                                +-- regression cases
    +--------- metrics --+---------> Prometheus
              API metrics ---------> Prometheus
              Dramatiq metrics ----> Prometheus
```

## Responsibilities

- **FastAPI**: grounded query API, bearer user authentication, owned conversation/history API,
  feedback API, health endpoints, protected operations API, request correlation, Prometheus API
  metrics, and optional OpenTelemetry tracing.
- **Scheduler**: periodically enqueue all enabled source IDs; it never performs ingestion work.
- **Worker**: source locks, crawling, parsing, code-aware chunking, embeddings, incremental indexing,
  and worker/model metrics.
- **Qdrant**: dense/sparse vectors, exact debug payload indexes, snapshot metadata, and chunks.
- **PostgreSQL**: user credential hashes, source/file state, ingestion runs, evaluations,
  conversations, answer traces, citations/verification snapshots, feedback, quality reviews, and
  reviewed regression cases.
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
request
  -> optional bearer API-key authentication
  -> conversation ownership check when conversation_id is supplied
  -> bounded completed history only for authenticated owner
  -> current question
  -> contextual follow-up rewrite only when deterministic rule says history is needed
  -> deterministic query router
  -> intent + source/version/ref/commit route
  -> Qdrant payload filter
  -> dense + BM25 retrieval
  -> exact debug lane when applicable
  -> RRF fusion
  -> cross-encoder reranking
  -> evidence threshold
  -> grounded generation with history marked context-only
  -> citation validation
  -> claim verification against current evidence
  -> final answer or abstention
  -> persist owned/anonymous interaction + citations + verification + timing trace
  -> optional ownership-checked feedback
```

The router currently recognizes SDK, EDC, DTR, semantic-model, release/version, debugging, and
general queries. Source filters are deliberately deterministic so routing decisions can be
inspected and benchmarked without adding another LLM call.

Semantic release versions such as `24.05` are extracted and preserved in the route but are not
used as a hard payload filter because a release repository can document several releases at the
same indexed ref. Explicit `ref:` and `commit:` constraints are hard filters and fail closed when
that indexed provenance is unavailable.

## Authentication and conversation ownership

The first user identity adapter uses opaque bearer API keys. An administrator creates or rotates a
key through the protected operations API. The plaintext token is returned once; PostgreSQL stores
only a SHA-256 digest and short prefix.

```text
Authorization: Bearer tm_<random-token>
          |
          v
       SHA-256
          |
          v
app_user.api_key_hash + enabled flag
          |
          v
       user_id
```

Authenticated conversations store `owner_user_id`. Access is fail-closed: a mismatched owner gets
`404`, not `403`, so the API does not reveal another user's conversation existence. Existing
anonymous conversations remain anonymous and are not automatically claimed.

Only authenticated owned conversations can contribute history to generation. Anonymous requests
remain supported, but anonymous history is never injected into a prompt.

History selection is bounded by `HISTORY_MAX_TURNS` and `HISTORY_MAX_CHARS`, and only completed
interactions are eligible. For likely follow-ups, the previous **user question** can be prepended to
the retrieval query. Previous assistant answers remain generation context only and never become
retrieval/source evidence.

The system prompt labels conversation history as untrusted context that must not be cited. Backend
citation validation and claim verification continue to operate exclusively on the current retrieved
source evidence.

See [`authenticated-conversations.md`](authenticated-conversations.md).

## Conversation and trace persistence

`conversation` groups related requests by an opaque UUID and optionally stores `owner_user_id`.
`answer_interaction` stores an immutable snapshot of a completed or failed answer request, including
route, citations, verification result, model, grounded/abstained outcome, request-local stage
durations, total duration, and OpenTelemetry trace ID when available.

The request-local timing collector is backed by `contextvars`, so concurrent API requests do not
share stage data. Prometheus remains the aggregate metric system; PostgreSQL stores the trace
snapshot needed to inspect one specific production answer.

`answer_feedback` stores one mutable `up` or `down` record per completed interaction. Re-submission
updates the same record. Feedback for an authenticated conversation is accepted only from the
conversation owner. Protected ops endpoints retain cross-user administrative inspection.

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

## Production evaluation gate

The production quality gate separates deterministic CI contracts from live-corpus evaluation.
Normal CI always tests gate logic. A dedicated quality workflow uses the real Qdrant corpus and LLM
when configured.

Hard invariants include zero unsafe-answer rate, zero unsafe evidence acceptance after calibration,
and 100% pass for human-reviewed regression cases. Seed retrieval metrics remain report-only until
full-corpus baselines are measured and versioned rather than guessed.

The calibrated minimum relevance threshold is expected to be explicitly reviewed and pinned. A
future calibration that materially drifts from the pinned threshold is a gate violation rather than
a silent production behavior change.

See [`quality-gate.md`](quality-gate.md).

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
11. Production evaluation gates over reviewed regressions and measured calibration
12. Authenticated user-owned bounded conversation history
13. Code-aware and graph-enhanced retrieval only when benchmark results justify it

Every answer should remain traceable to identity/ownership state when present,
repository/file/version/snapshot/content commit/chunk, retrieval evidence, verification result,
persisted interaction, optional feedback, and any reviewed regression case derived from it.
