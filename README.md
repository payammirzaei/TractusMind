# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem.**

TractusMind answers architecture, documentation, coding, debugging, semantic-model, and
version-specific questions using traceable Tractus-X sources. Retrieval quality, provenance,
inspectability, and measurable evaluation come before UI work.

## What is implemented

- FastAPI query API
- Qdrant dense + BM25 sparse retrieval
- exact debug phrase/symbol/path/config retrieval
- cross-encoder reranking
- deterministic source/version/ref/commit routing
- structure-aware Markdown/code/YAML/Turtle chunking
- OpenAI-compatible grounded generation
- backend-owned citations + atomic claim verification
- PostgreSQL incremental-ingestion state
- Redis + Dramatiq background source synchronization
- Prometheus metrics + optional OpenTelemetry traces
- persisted answer traces and feedback
- human-reviewed production regression loop
- production quality-gate workflow
- opaque bearer users + owned conversation history
- Alembic versioned PostgreSQL migrations
- Docker / Docker Compose / GitHub Actions

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Compose runs a one-shot database migration service before API and worker startup.

Local services:

```text
API          http://localhost:8000
OpenAPI      http://localhost:8000/docs
Metrics      http://localhost:8000/metrics
Prometheus   http://localhost:9090
Qdrant       http://localhost:6333/dashboard
```

Without Docker:

```bash
python -m pip install -e ".[dev]"
tractusmind-db bootstrap
ruff check .
pytest -q
```

## Database migrations

PostgreSQL schema changes are managed only through Alembic. Application requests and workers do
not call `create_all()` or mutate schema at runtime.

Current chain:

```text
0001_core_schema
  -> 0002_user_auth   (head)
```

Useful commands:

```bash
# Recommended deployment path; handles fresh, versioned, or complete legacy DBs
tractusmind-db bootstrap

# Normal versioned upgrade
tractusmind-db upgrade

# Verify DB matches this application build
tractusmind-db check

# Inspect revision state
tractusmind-db current
tractusmind-db history

# Explicit rollback; back up production first
tractusmind-db downgrade 0001_core_schema
```

`bootstrap` fails closed on partial legacy schemas instead of guessing around production data.
The API verifies the Alembic head during startup, and background ingestion verifies it before
source-state work begins.

See [`docs/database-migrations.md`](docs/database-migrations.md).

## Source registry and ingestion

Official Tractus-X sources are allowlisted in `config/sources.toml`. Repository refs are resolved
to immutable Git commit SHAs before content is fetched.

Useful commands:

```bash
tractusmind-ingest discover tractusx-sdk
tractusmind-ingest fetch tractusx-sdk --limit 3
tractusmind-ingest chunk tractusx-sdk --limit 3
tractusmind-ingest index tractusx-sdk --limit 10
tractusmind-ingest sync tractusx-sdk
```

Incremental sync compares Git blob SHAs and classifies files as:

```text
added
modified
deleted
unchanged
```

Only added and modified files are downloaded, chunked, embedded, and upserted. Unchanged files
receive metadata-only snapshot updates; deleted paths are removed.

PostgreSQL tracks:

```text
source_state
source_file_state
ingestion_run
```

Snapshot provenance distinguishes:

```text
snapshot_commit_sha = repository snapshot currently queried
commit_sha          = exact commit containing cited file content
```

See [`docs/incremental-ingestion.md`](docs/incremental-ingestion.md).

## Background source synchronization

```text
Scheduler
   ↓
Redis / Dramatiq
   ↓
Ingestion Worker
   ↓
per-source Redis lock
   ↓
IncrementalSourceSync
   ↓
PostgreSQL + Qdrant
```

Defaults:

```bash
SOURCE_SYNC_INTERVAL_SECONDS=21600
SOURCE_SYNC_LOCK_SECONDS=43200
```

Manual queue controls:

```bash
tractusmind-ingest enqueue tractusx-sdk
tractusmind-ingest enqueue-all
tractusmind-scheduler --once
tractusmind-scheduler
```

See [`docs/background-ingestion.md`](docs/background-ingestion.md).

## Retrieval pipeline

Normal queries:

```text
question
  -> deterministic route
  -> metadata/source/version filter
  -> dense retrieval
  -> BM25 sparse retrieval
  -> RRF fusion
  -> cross-encoder reranking
  -> evidence threshold
  -> final evidence
```

Debug queries add an exact lane:

```text
error / exception / symbol / config / path
  -> exact phrase/symbol/parent/path lookup
  -> normal hybrid retrieval
  -> weighted RRF
  -> cross-encoder reranking
```

Debug parsing recognizes quoted messages, exception classes, CamelCase/snake_case identifiers,
dotted config keys, paths, environment-style identifiers, and HTTP 4xx/5xx codes.

Every retrieval hit can preserve:

```text
source_id
repository
version_ref
snapshot_commit_sha
commit_sha
path
line range
source URL
retrieval_score
rerank_score
debug_score
retrieval_methods
```

## Grounded answer generation

Configure any OpenAI-compatible chat-completions endpoint:

```bash
LLM_BASE_URL=https://provider.example/v1
LLM_API_KEY=...
LLM_MODEL=...
```

Query:

```http
POST /v1/ask
Content-Type: application/json

{
  "question": "How do I create an asset with the Tractus-X SDK?"
}
```

Production path:

```text
question
  -> optional owned bounded conversation context
  -> routing
  -> retrieval + reranking
  -> bounded source evidence
  -> grounded generation
  -> backend citation validation
  -> atomic claim verification
  -> grounded answer or abstention
```

Evidence IDs such as `[S1]` are owned by the backend. The model cannot invent repository URLs,
source IDs, refs, commits, paths, or line numbers. Unsupported claims fail closed.

## Authenticated user-owned conversations

Anonymous `/v1/ask` remains supported, but anonymous history is never loaded into generation.

Admins create users under `/v1/ops/users`. The plaintext opaque API key is returned only when it
is created or rotated; PostgreSQL stores its SHA-256 digest and short prefix.

Clients send:

```http
Authorization: Bearer tm_...
```

Authenticated conversations have `owner_user_id`. Cross-user conversation access deliberately
returns `404` so existence is not leaked. Existing anonymous conversations are not auto-claimed.

Owned history reads:

```text
GET /v1/conversations
GET /v1/conversations/{conversation_id}
```

History is bounded by:

```bash
HISTORY_MAX_TURNS=6
HISTORY_MAX_CHARS=6000
```

History is context, **not source evidence**. Previous assistant answers cannot be cited. A true
follow-up may reuse the previous user question to improve retrieval, while current claims are still
verified only against current source evidence.

See [`docs/authenticated-conversations.md`](docs/authenticated-conversations.md) and
[`docs/conversation-feedback.md`](docs/conversation-feedback.md).

## Feedback-driven quality loop

```text
failed answer --------+
                      +-> pending quality review
user down-vote -------+          ↓
                           human root cause
                         /                \
                    dismiss             promote
                                           ↓
                                  regression case
                                           ↓
                                  benchmark NDJSON
                                           ↓
                                      CI/eval gate
```

Root-cause classes include routing, retrieval, citation, generation, verification, source data,
and versioning. Raw feedback never becomes a gold benchmark automatically.

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

Answer evaluation and threshold calibration:

```bash
tractusmind-answer-eval evaluate
tractusmind-answer-eval calibrate --max-unsafe-rate 0
```

Quality contract enforcement:

```bash
tractusmind-quality-gate \
  --calibration calibration.json \
  --answer answer.json \
  --require-pinned-threshold
```

Hard invariants currently require:

```text
unsafe answer rate              = 0
unsafe evidence acceptance rate = 0
reviewed retrieval regressions  = 100% pass
reviewed debug regressions      = 100% pass
reviewed answer regressions     = 100% pass
```

Aggregate seed MRR/NDCG/recall remain report-only until a measured full-corpus baseline is pinned.

See [`docs/quality-gate.md`](docs/quality-gate.md).

## Operations API

Configure:

```bash
OPS_ADMIN_KEY=replace-with-a-long-random-secret
```

Send:

```http
X-TractusMind-Admin-Key: replace-with-a-long-random-secret
```

Protected operations include:

```text
GET  /v1/ops/summary
GET  /v1/ops/sources
GET  /v1/ops/runs
GET  /v1/ops/interactions
GET  /v1/ops/users
GET  /v1/ops/quality/summary
GET  /v1/ops/quality/reviews
GET  /v1/ops/quality/regressions
POST /v1/ops/sources/{source_id}/sync
POST /v1/ops/sync
POST /v1/ops/users
POST /v1/ops/users/{user_id}/rotate
PATCH /v1/ops/users/{user_id}
```

See [`docs/operations.md`](docs/operations.md).

## Observability

Local Compose includes Prometheus. Main scrape surfaces:

```text
api:8000/metrics
worker:9101/metrics
worker:9191/
scheduler:9102/metrics
```

TractusMind records HTTP latency, retrieval/rerank/generation/verification latency, model warm-up,
ingestion duration/outcomes, queue state, lock contention, and answer outcomes. Every normal API
response receives `X-Request-ID` for log correlation.

Optional OTLP traces:

```bash
OTEL_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_SERVICE_NAME=tractusmind-api
OTEL_SAMPLE_RATIO=1.0
```

See [`docs/observability.md`](docs/observability.md).

## Inspectability principle

No hidden RAG magic. A production answer should remain inspectable as:

```text
identity / anonymous
  -> owned history when eligible
  -> question
  -> route
  -> source/ref/snapshot filter
  -> dense/sparse/exact candidates
  -> fusion + rerank scores
  -> evidence threshold
  -> final source evidence
  -> answer
  -> citations
  -> claim/evidence verdicts
  -> persisted interaction + timings + trace ID
  -> optional feedback
  -> optional human review
  -> reviewed regression gate
```

See [`docs/architecture.md`](docs/architecture.md).

## Current milestone

**V16 — Versioned Database Migrations + Production Schema Upgrade**

Completed:

- [x] source-grounded ingestion/retrieval/generation pipeline
- [x] version-aware routing and exact debug retrieval
- [x] citation and atomic claim verification
- [x] incremental PostgreSQL/Qdrant source synchronization
- [x] background scheduler/worker + distributed locks
- [x] operations API and production observability
- [x] persisted conversations, answer traces, feedback, and quality reviews
- [x] human-reviewed regression promotion and benchmark export
- [x] production quality-gate CLI/workflow
- [x] opaque bearer users and owned bounded conversation history
- [x] Alembic revision chain with upgrade/downgrade support
- [x] safe adoption of complete pre-Alembic legacy databases
- [x] fail-fast API/worker database revision guard
- [x] Compose migration-before-service startup
- [x] PostgreSQL CI migration, legacy-adoption, rollback, and re-upgrade smoke tests

Still measured/production-dependent:

- [ ] run full-corpus debug benchmark and tune fusion weights
- [ ] run live full-corpus abstention calibration and pin the measured threshold
- [ ] promote reviewed real production cases into committed regression files
- [ ] add production Grafana dashboards/alerts after measured traffic exists
- [ ] add OIDC/JWKS adapter if external enterprise SSO is required

## License

Apache-2.0
