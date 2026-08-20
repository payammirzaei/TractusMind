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
- production evaluation/quality gate
- Alembic versioned PostgreSQL migrations + drift checking
- Prometheus + optional OpenTelemetry
- provisioned Grafana dashboards + Alertmanager rules
- hardened production Compose topology + automatic TLS edge
- Docker secret-file loading, request limits, private networks, and resource guards
- Trivy security CI + tagged GHCR release images with SBOM/provenance

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

Production uses a separate topology:

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

Only Caddy publishes the application edge. PostgreSQL, Redis, and Qdrant have no host ports.
Grafana/Prometheus/Alertmanager bind only to loopback for SSH-tunneled operator access.

Production adds:

- automatic TLS + HSTS/security headers
- TrustedHost + explicit CORS policy
- request-body, rate, and concurrency guards
- interactive API docs disabled by default
- Docker `*_FILE` secrets instead of plaintext application credentials
- read-only application roots, dropped capabilities, `no-new-privileges`
- graceful shutdown and configurable CPU/memory limits
- pinned infrastructure release tags
- PostgreSQL backup/restore scripts
- Trivy filesystem/image security gates
- tagged multi-architecture GHCR images with SBOM/provenance

See [`docs/production-deployment.md`](docs/production-deployment.md).

## Database migrations

PostgreSQL schema changes are Alembic-only. Runtime code never silently creates or alters tables.

```text
0001_core_schema
  -> 0002_user_auth   (head)
```

```bash
tractusmind-db bootstrap
tractusmind-db upgrade
tractusmind-db check
tractusmind-db drift
tractusmind-db current
tractusmind-db history
```

See [`docs/database-migrations.md`](docs/database-migrations.md).

## Source synchronization

Official sources are allowlisted in `config/sources.toml`. Repository refs resolve to immutable Git
commits before content is fetched.

```bash
tractusmind-ingest discover tractusx-sdk
tractusmind-ingest fetch tractusx-sdk --limit 3
tractusmind-ingest chunk tractusx-sdk --limit 3
tractusmind-ingest index tractusx-sdk --limit 10
tractusmind-ingest sync tractusx-sdk
```

Incremental sync classifies files as added/modified/deleted/unchanged and only re-embeds changed
content. Provenance separates the repository snapshot from the exact content commit used by a
citation.

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
GET /v1/conversations
GET /v1/conversations/{conversation_id}
POST /v1/feedback
```

See [`docs/authenticated-conversations.md`](docs/authenticated-conversations.md) and
[`docs/conversation-feedback.md`](docs/conversation-feedback.md).

## Human-reviewed quality loop

```text
failed answer / down-vote
          |
          v
 pending quality review
          |
     human root cause
       /       \
  dismiss    promote
                |
         regression case
                |
         benchmark export
                |
          evaluation gate
```

Raw feedback never becomes gold data automatically.

See [`docs/quality-loop.md`](docs/quality-loop.md) and
[`docs/quality-gate.md`](docs/quality-gate.md).

## Observability

Prometheus captures API/RAG/model/provider/ingestion/worker/quality signals. Grafana ships with
provisioned API/RAG, provider/ingestion, and quality-loop dashboards. Alert rules cover target
availability, API errors/latency, provider circuit/retry pressure, pipeline errors, ingestion/worker
failures, and quality-review spikes.

```text
API metrics       /metrics
Grafana           3000
Prometheus        9090
Alertmanager      9093
```

Production operator ports bind only to `127.0.0.1`. Prometheus authenticates to the API metrics
endpoint using a Docker-secret Bearer credential.

See [`docs/observability.md`](docs/observability.md) and
[`docs/grafana-alerting.md`](docs/grafana-alerting.md).

## Backup

```bash
sh scripts/backup-postgres.sh
RESTORE_CONFIRM=YES sh scripts/restore-postgres.sh backups/<dump-file>
```

PostgreSQL and Qdrant must be recovered as a consistent set, or the vector corpus must be rebuilt
from immutable source repositories before answers are served.

## Current milestone

**V19 — Production Deployment & Security Hardening**

Completed:

- [x] source-grounded ingestion/retrieval/generation pipeline
- [x] version-aware routing + exact debug retrieval
- [x] grounded citations + atomic claim verification
- [x] incremental PostgreSQL/Qdrant synchronization
- [x] scheduler/worker + Redis distributed source locks
- [x] conversations, feedback, human quality review, and regression promotion
- [x] production evaluation gate
- [x] authenticated user-owned bounded history
- [x] versioned Alembic schema + legacy bootstrap + ORM drift gate
- [x] provider retries/idempotency/circuit breakers
- [x] Prometheus/OpenTelemetry/Grafana/Alertmanager observability
- [x] production-only Compose topology with private backend network
- [x] Caddy TLS edge and security headers
- [x] Docker secret-file application configuration
- [x] request-size/rate/concurrency/TrustedHost/CORS guards
- [x] production healthchecks, graceful shutdown, and resource limits
- [x] pinned infrastructure release tags
- [x] PostgreSQL backup/guarded restore tooling
- [x] Trivy filesystem + container image security workflow
- [x] tagged GHCR release image workflow with SBOM/provenance

Still measured/environment-dependent:

- [ ] run full-corpus debug benchmark and tune fusion weights
- [ ] run live full-corpus abstention calibration and pin measured threshold
- [ ] promote reviewed real production cases into committed regression files
- [ ] connect real Alertmanager receiver/secrets
- [ ] tune alerts and resource limits from measured traffic
- [ ] add distributed rate limiting when deploying multiple API replicas
- [ ] add OIDC/JWKS adapter if enterprise SSO is required

## License

Apache-2.0
