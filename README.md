# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem.**

TractusMind answers architecture, documentation, coding, debugging, semantic-model, and
version-specific questions using traceable Tractus-X sources. Retrieval quality, provenance,
inspectability, and measurable evaluation come before UI work.

## Foundation stack

- Python 3.12 + FastAPI
- Qdrant dense + BM25 sparse retrieval
- FastEmbed `BAAI/bge-small-en-v1.5` dense embeddings
- FastEmbed `Qdrant/bm25` sparse retrieval
- Qdrant RRF fusion
- Exact debug phrase/symbol/path/config retrieval
- FastEmbed cross-encoder reranking with `Xenova/ms-marco-MiniLM-L-6-v2`
- Deterministic version-aware query routing
- OpenAI-compatible grounded generation
- Claim-level answer verification
- PostgreSQL source/file state + ingestion-run history
- PostgreSQL conversation, answer-trace, citation, verification, feedback, and quality-review state
- Opaque bearer API keys + authenticated user-owned conversation history
- Redis + Dramatiq background ingestion
- Protected ingestion, interaction, user, and quality operations API
- Feedback-driven reviewed regression cases
- Production quality-gate CLI + GitHub Actions workflow
- Prometheus metrics + optional OpenTelemetry traces
- Tree-sitter structure-aware code chunking
- Docker / Docker Compose
- GitHub Actions

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- API metrics: `http://localhost:8000/metrics`
- Prometheus: `http://localhost:9090`
- Qdrant: `http://localhost:6333/dashboard`
- Dramatiq ingestion worker
- scheduled source-sync service
- PostgreSQL
- Redis

Without Docker:

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
```

## Source registry and ingestion

Official Tractus-X sources are allowlisted in `config/sources.toml`. Every repository ref is
resolved to an immutable Git commit before content is fetched.

Useful commands:

```bash
tractusmind-ingest discover tractusx-sdk
tractusmind-ingest fetch tractusx-sdk --limit 3
tractusmind-ingest chunk tractusx-sdk --limit 3
tractusmind-ingest index tractusx-sdk --limit 10
```

For production-shaped source maintenance, use incremental synchronization:

```bash
tractusmind-ingest sync tractusx-sdk
```

The first managed sync establishes PostgreSQL state. Later syncs compare the new manifest against
stored Git blob SHAs and divide files into:

```text
added
modified
deleted
unchanged
```

Only `added` and `modified` files are downloaded, chunked, embedded, and upserted. Unchanged files
receive a metadata-only snapshot update in Qdrant. Deleted paths are removed.

PostgreSQL stores:

- `source_state`: current successful source snapshot.
- `source_file_state`: path + Git blob fingerprint + content commit per file.
- `ingestion_run`: auditable run history and delta counters.

See [`docs/incremental-ingestion.md`](docs/incremental-ingestion.md).

## Snapshot and citation provenance

Incremental indexing keeps two commit identities:

```text
snapshot_commit_sha = repository snapshot currently being queried
commit_sha          = exact commit containing the cited file content
```

If a file does not change between repository commits, TractusMind does **not** re-embed it. Its
`snapshot_commit_sha` moves forward while its exact content commit and commit-pinned source URL
remain unchanged.

This preserves both efficient incremental ingestion and exact citations.

## Background ingestion

TractusMind can keep the allowlisted corpus fresh without a human running the sync CLI.

```text
Scheduler
   ↓
Redis / Dramatiq
   ↓
Ingestion Worker
   ↓
per-source distributed Redis lock
   ↓
IncrementalSourceSync
   ↓
PostgreSQL + Qdrant
```

The default scheduler queues all enabled sources immediately on startup and then every six hours:

```bash
SOURCE_SYNC_INTERVAL_SECONDS=21600
```

A per-source Redis distributed lock prevents two workers from synchronizing the same source at the
same time:

```bash
SOURCE_SYNC_LOCK_SECONDS=43200
```

The default Compose worker uses one process and one thread because an indexing job may load dense
and sparse embedding models into memory. Multiple worker replicas can still be added because the
source lock is shared through Redis.

Manual queue controls:

```bash
# queue one source
tractusmind-ingest enqueue tractusx-sdk

# queue every enabled source
tractusmind-ingest enqueue-all

# run one scheduler cycle
tractusmind-scheduler --once

# long-running scheduler
tractusmind-scheduler
```

The worker actor retries runtime failures through the same idempotent incremental sync path.

See [`docs/background-ingestion.md`](docs/background-ingestion.md).

## Operations API

Source maintenance and internal quality state are inspectable through a protected API. Configure a
strong admin key:

```bash
OPS_ADMIN_KEY=replace-with-a-long-random-secret
```

Send it as:

```http
X-TractusMind-Admin-Key: replace-with-a-long-random-secret
```

If the key is not configured, the entire `/v1/ops/*` surface returns `503`; it never silently
falls back to public access.

Core reads:

```text
GET /v1/ops/summary
GET /v1/ops/sources
GET /v1/ops/sources/{source_id}
GET /v1/ops/runs
GET /v1/ops/runs/{run_id}
GET /v1/ops/interactions
GET /v1/ops/feedback/summary
GET /v1/ops/users
GET /v1/ops/quality/summary
GET /v1/ops/quality/reviews
GET /v1/ops/quality/regressions
```

Manual source triggers enqueue work instead of running ingestion inside the HTTP request:

```text
POST /v1/ops/sources/{source_id}/sync
POST /v1/ops/sync
```

User credential administration is also protected by the same admin key:

```text
POST  /v1/ops/users
POST  /v1/ops/users/{user_id}/rotate
PATCH /v1/ops/users/{user_id}
```

See [`docs/operations.md`](docs/operations.md), [`docs/quality-loop.md`](docs/quality-loop.md), and
[`docs/authenticated-conversations.md`](docs/authenticated-conversations.md).

## Observability

The local Compose stack includes Prometheus at `http://localhost:9090`. It scrapes four process
surfaces:

```text
api:8000/metrics       -> HTTP + answer-pipeline metrics
worker:9101/metrics    -> TractusMind ingestion/model/worker metrics
worker:9191/           -> native Dramatiq queue/runtime metrics
scheduler:9102/metrics -> scheduled enqueue metrics
```

The API records latency using FastAPI **route templates**, not arbitrary request paths. Grounded
answer stages expose separate retrieval, generation, and verification latency plus answer-outcome
counters. Dense, sparse, and reranker runtime metrics expose first-use warm-up and operation
latency. Background ingestion exposes success/failure/lock-contention counts, duration, and file
delta classifications.

Every normal API response gets `X-Request-ID`, and the same value is bound into structured log
context. When OpenTelemetry tracing is active, the trace ID is bound to logs as well.

Metric labels are intentionally low-cardinality. User questions, source-code text, error messages,
raw paths, commit SHAs, chunk IDs, request IDs, trace IDs, and credentials are never metric labels.

Metrics are open only in development. In non-development environments configure
`METRICS_ADMIN_KEY` or reuse `OPS_ADMIN_KEY` and send `X-TractusMind-Metrics-Key` when scraping the
API endpoint. Worker/scheduler metric ports are intended for private-network scraping.

Optional OTLP/HTTP traces:

```bash
OTEL_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_SERVICE_NAME=tractusmind-api
OTEL_SAMPLE_RATIO=1.0
```

Without `OTEL_TRACES_ENDPOINT`, tracing export is disabled. With it configured, FastAPI creates the
server span and TractusMind adds child spans for retrieval, generation, and verification.

See [`docs/observability.md`](docs/observability.md) for metric families, security rules, and
example PromQL.

## Smart chunking

Fetched files become canonical `RawDocument` objects with stable IDs, version ref, exact commit,
blob SHA, language/content type, normalized UTF-8 text, content hash, and commit-pinned URL.

Chunkers preserve source structure:

- Markdown: heading hierarchy
- Python / Java / Kotlin / TypeScript / JavaScript: Tree-sitter symbols
- code: parent symbol relationships
- YAML: top-level logical objects
- Turtle / SAMM: semantic statements
- every chunk: exact line range + source provenance

## Version-aware query routing

Before retrieval, a deterministic router detects:

- SDK
- EDC
- Digital Twin Registry / DTR
- Semantic Models / SAMM
- Release/version questions
- Debug/error questions
- General fallback

The route records intent, selected source IDs, semantic version, explicit `ref:`, explicit
`commit:`, and routing reasons.

Examples:

```bash
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?"
tractusmind-ingest search "EDC connector returns 500 error during transfer"
tractusmind-ingest search "What changed for SAMM in release 24.05?"
tractusmind-ingest search "Check EDC ref:v0.9.0 commit:abcdef1234567 connector behavior"
```

Explicit `commit:` selects the indexed repository snapshot via `snapshot_commit_sha`.

## Retrieval pipeline

Normal questions:

```text
question
  -> route + metadata filter
  -> dense retrieval
  -> BM25 sparse retrieval
  -> Qdrant RRF
  -> cross-encoder reranking
  -> final evidence
```

Debug questions add an exact-search lane:

```text
error / stacktrace / symbol / config / path
  -> exact phrase + symbol + parent-symbol + path lookup
  -> normal dense + BM25 retrieval
  -> weighted RRF across exact + hybrid candidates
  -> cross-encoder reranking
  -> final evidence
```

Debug query parsing recognizes quoted error messages, exception classes, CamelCase and snake_case
identifiers, dotted config keys, paths, environment-style identifiers, and HTTP 4xx/5xx codes.

Every hit can preserve:

```text
retrieval_score
rerank_score
debug_score
retrieval_methods
snapshot_commit_sha
commit_sha
source URL + exact lines
```

## Grounded answer generation

Configure an OpenAI-compatible chat-completions provider:

```bash
LLM_BASE_URL=https://provider.example/v1
LLM_API_KEY=...
LLM_MODEL=...
```

Ask through:

```http
POST /v1/ask
Content-Type: application/json

{
  "question": "How do I create an asset with the Tractus-X SDK?"
}
```

Production answer path:

```text
question
  -> optional authenticated bounded history context
  -> routing
  -> retrieval
  -> reranking
  -> bounded source-evidence context
  -> grounded LLM generation
  -> backend citation validation
  -> atomic claim verification
  -> answer or abstention
```

The backend owns evidence IDs such as `[S1]`. The model is not trusted to invent repository URLs,
source IDs, refs, commits, paths, or line numbers. Structured citation IDs must match inline
citations, and unsupported claims fail closed.

## Authenticated conversations, trace, and feedback

Completed and failed answer requests are persisted in PostgreSQL. Anonymous `/v1/ask` remains
supported, but anonymous history is never loaded into generation.

Administrators can create an end-user credential through `/v1/ops/users`. The plaintext opaque API
key is returned once; PostgreSQL stores only its SHA-256 digest and short prefix. Clients send it as:

```http
Authorization: Bearer tm_...
```

Authenticated conversations store an `owner_user_id`. A user can continue or read only their own
conversation. Cross-user access deliberately returns `404` so conversation existence is not leaked.
Existing anonymous conversations are never automatically claimed.

User-owned history endpoints:

```text
GET /v1/conversations
GET /v1/conversations/{conversation_id}
```

A later authenticated request can reuse its owned `conversation_id`:

```json
{
  "question": "What about contract negotiation?",
  "conversation_id": "..."
}
```

Only completed recent turns are loaded, bounded by:

```bash
HISTORY_MAX_TURNS=6
HISTORY_MAX_CHARS=6000
```

Conversation history is explicitly marked as context, **not evidence**. It cannot be cited. Short
context-dependent follow-ups may use the previous user question to improve routing/retrieval, but
previous assistant answers never become source evidence. Atomic claim verification still uses the
current question and current source evidence.

Feedback on an authenticated interaction is accepted only from the owning user. Anonymous
interactions retain the existing capability-style feedback behavior.

See [`docs/conversation-feedback.md`](docs/conversation-feedback.md) and
[`docs/authenticated-conversations.md`](docs/authenticated-conversations.md).

## Feedback-driven quality loop

Failed answer interactions and down-voted answers create idempotent quality-review candidates. Raw
feedback is a signal, not ground truth. An admin must classify a root cause and explicitly dismiss
or promote the review.

Supported root-cause classes include routing, retrieval, citation, generation, verification,
source-data, and versioning problems. Promoted cases become immutable reviewed regression cases and
can be exported in benchmark-compatible NDJSON.

Reviewed regression files live under:

```text
benchmarks/regressions/retrieval.jsonl
benchmarks/regressions/debug.jsonl
benchmarks/regressions/answer.jsonl
```

See [`docs/quality-loop.md`](docs/quality-loop.md).

## Evaluation and production quality gate

General retrieval benchmark:

```bash
tractusmind-benchmark --mode all --k 5
```

Debug retrieval benchmark:

```bash
tractusmind-benchmark \
  --dataset benchmarks/debug_v0.jsonl \
  --mode rerank \
  --k 5
```

Calibrate abstention without an LLM call:

```bash
tractusmind-answer-eval calibrate --max-unsafe-rate 0
```

Run end-to-end answer evaluation with an LLM configured:

```bash
tractusmind-answer-eval evaluate
```

Enforce versioned safety/regression contracts from generated reports:

```bash
tractusmind-quality-gate \
  --calibration calibration.json \
  --answer answer.json \
  --require-pinned-threshold
```

The live `.github/workflows/quality-gate.yml` uses the real indexed Qdrant corpus and configured LLM
when quality-gate secrets are available. Seed MRR/NDCG/recall remain report-only until measured
full-corpus baselines are pinned. Hard invariants already require zero unsafe answer/evidence accept
rate and 100% pass for reviewed regressions.

See [`docs/quality-gate.md`](docs/quality-gate.md).

## Inspectability principle

No hidden RAG magic. A production answer should remain inspectable as:

```text
authenticated identity / anonymous
  -> owned bounded history when eligible
  -> question
  -> route
  -> source/ref/snapshot filter
  -> dense/sparse/exact candidates
  -> fusion scores
  -> rerank scores
  -> evidence threshold
  -> final evidence
  -> generated answer
  -> citations
  -> atomic claims
  -> claim/evidence verdicts
  -> answer or abstention
  -> persisted interaction + timings + trace ID
  -> optional user feedback
  -> optional human quality review
  -> reviewed regression gate
```

See [`docs/architecture.md`](docs/architecture.md).

## Current milestone

**V15 — Authenticated User-Owned Conversations + Safe History Context**

- [x] source-grounded FastAPI query service
- [x] allowlisted Tractus-X source registry
- [x] immutable commit-pinned GitHub discovery and fetch
- [x] structure-aware documentation/code/semantic chunking
- [x] dense + BM25 hybrid retrieval
- [x] cross-encoder reranking
- [x] version-aware deterministic routing
- [x] exact debugging retrieval lane
- [x] grounded generation + backend-owned citations
- [x] atomic claim verification + fail-closed answer gate
- [x] retrieval/answer evaluation and abstention calibration tooling
- [x] PostgreSQL source/file state
- [x] incremental fetch/chunk/embed/index
- [x] snapshot-commit versus content-commit provenance
- [x] ingestion-run audit history
- [x] Dramatiq background source-sync actor
- [x] Redis distributed per-source lock
- [x] configurable scheduled sync of all enabled sources
- [x] admin-key-protected operations API
- [x] source/run/failure/lock operations visibility
- [x] Prometheus API/RAG/model/ingestion/scheduler metrics
- [x] native Dramatiq queue/runtime Prometheus metrics
- [x] route-template HTTP latency + request-ID log correlation
- [x] optional OTLP/HTTP OpenTelemetry traces
- [x] persisted conversations and completed/failed interactions
- [x] up/down feedback + protected interaction inspection
- [x] automatic failed/down-vote quality-review capture
- [x] human root-cause review + immutable regression promotion
- [x] benchmark-compatible reviewed regression export
- [x] production quality-gate CLI and live workflow
- [x] opaque bearer user credentials with hashed-at-rest keys
- [x] admin create/rotate/disable user credential lifecycle
- [x] authenticated conversation ownership and fail-closed cross-user access
- [x] bounded owned conversation history in generation
- [x] contextual follow-up retrieval using previous user question only
- [x] authenticated feedback ownership enforcement
- [x] authenticated owned history read API
- [ ] run full-corpus debug benchmark and tune fusion weights
- [ ] run live full-corpus abstention calibration and pin the measured threshold
- [ ] promote reviewed real production cases into committed regression files
- [ ] add versioned database migrations before externally managed schema deployment
- [ ] add production Grafana dashboards/alerts after measured traffic exists
- [ ] add OIDC/JWKS identity adapter if external enterprise SSO is required

## License

Apache-2.0