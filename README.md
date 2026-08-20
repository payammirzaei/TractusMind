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
- bounded LLM/GitHub retries + process-shared circuit breakers
- stable LLM idempotency key across transient retries
- PostgreSQL incremental-ingestion state
- Redis + Dramatiq background source synchronization
- Prometheus metrics + optional OpenTelemetry traces
- Grafana dashboards + Prometheus alert rules + Alertmanager
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
Grafana      http://localhost:3000
Prometheus   http://localhost:9090
Alertmanager http://localhost:9093
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
tractusmind-db bootstrap
tractusmind-db upgrade
tractusmind-db check
tractusmind-db drift
tractusmind-db current
tractusmind-db history
tractusmind-db downgrade 0001_core_schema
```

`bootstrap` handles fresh, versioned, or complete pre-Alembic TractusMind databases and fails
closed on partial legacy schemas. `drift` fails if ORM metadata differs from the migrated schema.

See [`docs/database-migrations.md`](docs/database-migrations.md).

## Source registry and ingestion

Official Tractus-X sources are allowlisted in `config/sources.toml`. Repository refs are resolved
to immutable Git commit SHAs before content is fetched.

```bash
tractusmind-ingest discover tractusx-sdk
tractusmind-ingest fetch tractusx-sdk --limit 3
tractusmind-ingest chunk tractusx-sdk --limit 3
tractusmind-ingest index tractusx-sdk --limit 10
tractusmind-ingest sync tractusx-sdk
```

Incremental sync compares Git blob SHAs and classifies files as `added`, `modified`, `deleted`, or
`unchanged`. Only changed files are fetched/chunked/embedded; unchanged files receive metadata-only
snapshot updates.

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

Manual controls:

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

Debug queries add an exact phrase/symbol/parent/path lane before weighted fusion and reranking.
Every hit preserves source/version/snapshot/content-commit/path/line provenance plus retrieval and
rerank diagnostics.

## Grounded answer generation

Configure any OpenAI-compatible chat-completions endpoint:

```bash
LLM_BASE_URL=https://provider.example/v1
LLM_API_KEY=...
LLM_MODEL=...
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

Evidence IDs such as `[S1]` are owned by the backend. Unsupported claims fail closed.

## Provider resilience

LLM and GitHub are treated as unreliable external boundaries. Transient failures use bounded
exponential backoff with jitter; permanent client/auth errors fail immediately.

Defaults:

```bash
GITHUB_TIMEOUT_SECONDS=30
GITHUB_MAX_ATTEMPTS=4
LLM_TIMEOUT_SECONDS=60
LLM_MAX_ATTEMPTS=3
PROVIDER_RETRY_BASE_SECONDS=0.5
PROVIDER_RETRY_MAX_SECONDS=8
PROVIDER_CIRCUIT_FAILURE_THRESHOLD=3
PROVIDER_CIRCUIT_COOLDOWN_SECONDS=30
```

One `Idempotency-Key` is reused across retries of the same logical LLM call. Circuit breakers are
shared within each process and use a single half-open probe after cooldown.

See [`docs/provider-resilience.md`](docs/provider-resilience.md).

## Authenticated user-owned conversations

Anonymous `/v1/ask` remains supported, but anonymous history is never loaded into generation.
Admins create users under `/v1/ops/users`; plaintext opaque API keys are returned only when created
or rotated, while PostgreSQL stores only their SHA-256 digest and short prefix.

```http
Authorization: Bearer tm_...
```

Authenticated conversations have `owner_user_id`. Cross-user access deliberately returns `404`.
History is bounded by:

```bash
HISTORY_MAX_TURNS=6
HISTORY_MAX_CHARS=6000
```

History is context, **not source evidence**. Previous assistant answers cannot be cited.

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

Raw feedback never becomes a gold benchmark automatically. Reviewed regression files remain
human-approved artifacts under `benchmarks/regressions/`.

See [`docs/quality-loop.md`](docs/quality-loop.md).

## Evaluation and production quality gate

```bash
tractusmind-benchmark --mode all --k 5
tractusmind-answer-eval evaluate
tractusmind-answer-eval calibrate --max-unsafe-rate 0
tractusmind-quality-gate \
  --calibration calibration.json \
  --answer answer.json \
  --require-pinned-threshold
```

Hard invariants require zero unsafe answer/evidence acceptance and 100% pass for reviewed
retrieval, debug, and answer regressions. Aggregate seed MRR/NDCG/recall remain report-only until a
measured full-corpus baseline is pinned.

See [`docs/quality-gate.md`](docs/quality-gate.md).

## Operations API

Configure `OPS_ADMIN_KEY` and send it as `X-TractusMind-Admin-Key`.
Protected operations cover source/run state, interactions, users, quality reviews/regressions, and
manual source-sync enqueue controls.

See [`docs/operations.md`](docs/operations.md).

## Grafana, Prometheus, and alerting

V18 provisions three Grafana dashboards under the `TractusMind` folder:

```text
TractusMind — API & RAG Overview
TractusMind — Providers & Ingestion
TractusMind — Quality Loop
```

Prometheus loads repository-owned alert rules for target availability, API 5xx/latency, provider
retry/circuit pressure, RAG pipeline errors, negative-feedback/failure-review spikes, ingestion
failures, worker failures, and lock contention.

Alertmanager groups and routes alerts. Its repository default receiver intentionally has no external
Slack/email/PagerDuty/webhook credentials; deployments add those through their secret-management
system.

New quality-loop metric families include:

```text
tractusmind_quality_review_signals_total
tractusmind_quality_review_decisions_total
tractusmind_quality_regression_promotions_total
```

Exact pending-review backlog remains a PostgreSQL/ops-API state, not a fake Prometheus gauge.
Likewise, `tractusmind_queue_enqueued_total` is an enqueue counter and is not presented as queue
depth.

CI validates Prometheus config/rules with `promtool`, Alertmanager with `amtool`, all Grafana JSON,
and the full Compose configuration.

See [`docs/observability.md`](docs/observability.md) and
[`docs/grafana-alerting.md`](docs/grafana-alerting.md).

## Inspectability principle

No hidden RAG magic. A production answer remains inspectable as:

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
  -> bounded provider request/retry path
  -> answer
  -> citations
  -> claim/evidence verdicts
  -> persisted interaction + timings + trace ID
  -> optional feedback/review
  -> reviewed regression gate
```

See [`docs/architecture.md`](docs/architecture.md).

## Current milestone

**V18 — Production Grafana + Alerting**

Completed:

- [x] source-grounded ingestion/retrieval/generation pipeline
- [x] version-aware routing and exact debug retrieval
- [x] citation and atomic claim verification
- [x] incremental PostgreSQL/Qdrant source synchronization
- [x] background scheduler/worker + distributed locks
- [x] persisted conversations, feedback, and human-reviewed quality loop
- [x] production quality-gate CLI/workflow
- [x] opaque bearer users and owned bounded conversation history
- [x] Alembic versioned schema + legacy bootstrap + ORM drift gate
- [x] bounded LLM/GitHub retries, Retry-After handling, and circuit breakers
- [x] Prometheus + optional OpenTelemetry observability
- [x] provisioned Grafana API/RAG, provider/ingestion, and quality dashboards
- [x] Prometheus production-shaped alert rules
- [x] Alertmanager grouping/routing baseline
- [x] quality-loop Prometheus event metrics
- [x] CI validation for Prometheus, Alertmanager, Grafana JSON, and Compose

Still measured/production-dependent:

- [ ] run full-corpus debug benchmark and tune fusion weights
- [ ] run live full-corpus abstention calibration and pin the measured threshold
- [ ] promote reviewed real production cases into committed regression files
- [ ] connect the deployment's real Alertmanager notification receiver and secrets
- [ ] tune alert thresholds after measured production traffic exists
- [ ] add OIDC/JWKS adapter if external enterprise SSO is required

## License

Apache-2.0
