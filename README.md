# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem.**

TractusMind answers architecture, documentation, coding, debugging, semantic-model, and
version-specific questions using traceable Tractus-X sources. Retrieval quality, provenance,
inspectability, production safety, and measurable evaluation come before UI work.

## What is implemented

- FastAPI source-grounded query API
- allowlisted, commit-pinned Tractus-X GitHub ingestion
- structure-aware Markdown/code/YAML/Turtle chunking
- Qdrant dense + BM25 sparse hybrid retrieval
- exact debug phrase/symbol/path/config retrieval lane
- RRF fusion + cross-encoder reranking
- deterministic source/version/ref/commit routing
- OpenAI-compatible grounded generation
- backend-owned citations + atomic claim verification
- bounded provider retries, Retry-After handling, idempotency, and circuit breakers
- PostgreSQL incremental-ingestion and audit state
- Redis + Dramatiq background source synchronization
- persisted conversations, traces, and user feedback
- opaque bearer users + owned bounded conversation history
- human-reviewed feedback/failure regression loop
- Alembic versioned PostgreSQL migrations + drift checking
- Prometheus + optional OpenTelemetry
- provisioned Grafana dashboards + Alertmanager rules
- hardened production Compose topology + automatic TLS edge
- Docker secret-file loading, request limits, private networks, and resource guards
- Trivy security CI + tagged GHCR release images with SBOM/provenance
- six-source full-corpus validation and calibration workflow
- upstream freshness-aware corpus contract
- production quality gate over V1 retrieval/answer datasets

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Local services:

```text
API          http://localhost:8000
OpenAPI      http://localhost:8000/docs
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

## Production deployment

Production uses `docker-compose.prod.yml` with Caddy as the only public edge.

```text
Internet
   |
   | TLS 443
   v
 Caddy
   |
 FastAPI API ------------------ provider egress / LLM
   |
   +------------- internal backend -------------+
   |          |          |          |            |
Postgres    Redis      Qdrant   Prometheus    Grafana
                         ^          |
                         |      Alertmanager
                      Worker -------- provider egress / GitHub
```

Start from:

```bash
cp .env.production.example .env.production
mkdir -p secrets
# populate secrets/* as documented

docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

PostgreSQL, Redis, and Qdrant have no public host ports. Grafana, Prometheus, and Alertmanager bind
only to loopback for operator access.

See [`docs/production-deployment.md`](docs/production-deployment.md).

## Source synchronization

Official sources are allowlisted in `config/sources.toml`. Repository refs resolve to immutable Git
commits before content is fetched.

```bash
tractusmind-ingest discover tractusx-sdk
tractusmind-ingest sync tractusx-sdk
tractusmind-ingest enqueue-all
```

Incremental synchronization re-embeds only changed files and keeps repository snapshot provenance
separate from the exact content commit used for citations.

See [`docs/incremental-ingestion.md`](docs/incremental-ingestion.md) and
[`docs/background-ingestion.md`](docs/background-ingestion.md).

## Retrieval and grounded answers

```text
question
  -> owned bounded history when eligible
  -> deterministic route
  -> source/ref/snapshot filter
  -> dense + BM25 retrieval
  -> exact debug lane when applicable
  -> RRF fusion
  -> cross-encoder reranking
  -> calibrated evidence threshold
  -> grounded generation
  -> citation validation
  -> atomic claim verification
  -> answer or abstention
```

History is context, not evidence. Previous assistant answers cannot become source citations.
Explicit `ref:` and `commit:` constraints fail closed when indexed provenance is unavailable.

## Full-corpus validation

V20 defines a benchmark run as valid only after the corpus itself passes a fail-closed contract.

```bash
tractusmind-corpus-validate --verify-upstream
```

For every enabled source the validator checks:

- PostgreSQL successful source state
- matching successful ingestion run
- configured repository/component/ref identity
- Qdrant chunks for the same snapshot
- no stale chunks from older snapshots
- current upstream GitHub ref equals the indexed snapshot

The V1 benchmark sets cover every enabled source:

```text
benchmarks/full_corpus_v1.jsonl
benchmarks/answer_v1.jsonl
benchmarks/debug_v0.jsonl
```

The six enabled knowledge sources are SDK, EDC, Digital Twin Registry, semantic models,
Tractus-X documentation, and Tractus-X release metadata.

### Measurement workflow

`.github/workflows/full-corpus-validation.yml` uses the dedicated GitHub `quality` environment:

```text
optional full incremental refresh
        ↓
corpus + upstream freshness validation
        ↓
dense / hybrid / rerank benchmark
        ↓
debug benchmark
        ↓
zero-unsafe evidence calibration
        ↓
answer evaluation at measured threshold
        ↓
reviewed regressions
        ↓
validation-summary.json
        ↓
pin-candidate.toml
```

The workflow records source/upstream commits, model identities, registry/config/dataset SHA-256
values, retrieval metrics, answer metrics, and the measured threshold in a 90-day artifact.

**The measured threshold is never auto-committed.** Human review is required before copying it into
`config/quality_gate.toml`.

See [`docs/full-corpus-validation.md`](docs/full-corpus-validation.md).

## Production quality gate

After a full-corpus threshold has been reviewed and pinned, the weekly production quality gate:

1. rejects missing, inconsistent, or stale corpus snapshots;
2. recalibrates against `answer_v1.jsonl`;
3. rejects threshold drift beyond the configured tolerance;
4. requires zero unsafe answer rate;
5. requires zero unsafe evidence acceptance;
6. requires every committed human-reviewed regression to pass.

Raw feedback never becomes gold data automatically.

See [`docs/quality-loop.md`](docs/quality-loop.md) and
[`docs/quality-gate.md`](docs/quality-gate.md).

## Provider resilience

LLM and GitHub calls use bounded retries for transient failures, exponential backoff with jitter,
provider rate-limit delays, and process-shared circuit breakers. One stable `Idempotency-Key` is
reused for retries of one logical LLM call.

See [`docs/provider-resilience.md`](docs/provider-resilience.md).

## Authenticated conversations and feedback

Admins create opaque bearer credentials through the protected operations API. PostgreSQL stores
only token digests/prefixes. Authenticated conversations have an owner and cross-user access returns
`404` to avoid leaking existence.

```text
GET  /v1/conversations
GET  /v1/conversations/{conversation_id}
POST /v1/feedback
```

See [`docs/authenticated-conversations.md`](docs/authenticated-conversations.md) and
[`docs/conversation-feedback.md`](docs/conversation-feedback.md).

## Observability

Prometheus captures API/RAG/model/provider/ingestion/worker/quality signals. Grafana ships with
provisioned API/RAG, provider/ingestion, and quality-loop dashboards. Alert rules cover availability,
API errors/latency, provider pressure, pipeline failures, ingestion failures, and quality-review
signals.

See [`docs/observability.md`](docs/observability.md) and
[`docs/grafana-alerting.md`](docs/grafana-alerting.md).

## Database migrations

PostgreSQL schema changes are Alembic-only. Runtime code never silently creates or alters tables.

```bash
tractusmind-db bootstrap
tractusmind-db upgrade
tractusmind-db check
tractusmind-db drift
```

See [`docs/database-migrations.md`](docs/database-migrations.md).

## Current milestone

**V20 — Full-Corpus Validation & Calibration**

Completed in code and CI contracts:

- [x] fail-closed corpus validator across every enabled source
- [x] PostgreSQL source/run consistency verification
- [x] Qdrant current-snapshot and stale-snapshot verification
- [x] optional upstream GitHub ref freshness verification
- [x] six-source retrieval benchmark V1
- [x] six-source answer/abstention benchmark V1
- [x] CI contract requiring benchmark coverage for every enabled source
- [x] dedicated full-corpus refresh/measurement workflow
- [x] reproducible validation manifest with source/model/input hashes
- [x] measured-threshold candidate evaluated before pinning
- [x] production quality workflow upgraded from seed V0 to V1 full-corpus contracts
- [x] pinned-threshold drift enforcement
- [x] reviewed regression enforcement remains fail-closed

Requires a real configured `quality` environment before numerical claims can be made:

- [ ] execute the first complete full-corpus V20 run
- [ ] inspect retrieval/debug/answer metrics from the artifact
- [ ] review and pin the measured `minimum_relevance_score`
- [ ] rerun the production gate with the pinned value
- [ ] tune debug fusion weights only if measured results justify a change
- [ ] promote reviewed real production cases into committed regression files

Later milestones:

- enterprise OIDC/JWKS identity adapter when needed
- distributed rate limiting when multiple API replicas are deployed
- UI / Mission Control after the backend quality contract is proven

## License

Apache-2.0
