# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem.**

TractusMind answers architecture, documentation, coding, debugging, semantic-model, and
version-specific questions using traceable Tractus-X sources. Retrieval quality, provenance,
inspectability, production safety, and measurable evaluation come before UI work.

## What is implemented

- FastAPI source-grounded query API
- allowlisted, commit-pinned Tractus-X GitHub ingestion
- structure-aware Markdown/code/YAML/Turtle chunking
- Qdrant dense + BM25 hybrid retrieval + exact debug lane
- RRF fusion + cross-encoder reranking
- deterministic source/version/ref/commit routing
- OpenAI-compatible grounded generation
- backend-owned citations + atomic claim verification
- bounded provider retries, idempotency, and circuit breakers
- incremental PostgreSQL/Qdrant source synchronization
- Redis + Dramatiq background ingestion
- persisted conversations, traces, feedback, and human quality review
- API-key identities + enterprise OIDC/JWKS bearer authentication
- user/operator/admin RBAC + stable user-owned conversation history
- Alembic migrations + ORM drift checks
- six-source full-corpus validation + calibration workflow
- production quality gate + reviewed regressions
- Prometheus/OpenTelemetry/Grafana/Alertmanager observability
- hardened production Compose + Caddy TLS + Docker secrets
- Trivy security CI + GHCR release images with SBOM/provenance

## Local development

```bash
cp .env.example .env
docker compose up --build
```

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

Production uses `docker-compose.prod.yml` with Caddy as the public TLS edge. PostgreSQL, Redis, and
Qdrant are private; Grafana/Prometheus/Alertmanager bind only to loopback for operator access.

```bash
cp .env.production.example .env.production
mkdir -p secrets
# populate secrets/* as documented

docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

See [`docs/production-deployment.md`](docs/production-deployment.md).

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

## Authentication and RBAC

TractusMind accepts either self-contained opaque API keys or verified OIDC access tokens:

```text
Authorization: Bearer tm_...
             or
Authorization: Bearer <OIDC JWT>
```

OIDC uses standard discovery + JWKS and verifies issuer, expiry, configured audience, allowed
algorithm, and signing key. Unknown `kid` values trigger one JWKS refresh for normal key rotation.

```bash
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://id.example.com/realms/tractusmind
OIDC_AUDIENCE=tractusmind-api
OIDC_ALLOWED_ALGORITHMS=RS256
OIDC_ROLE_CLAIMS=roles,realm_access.roles,groups
OIDC_ADMIN_ROLES=tractusmind-admin
OIDC_OPERATOR_ROLES=tractusmind-operator
```

Roles are hierarchical:

```text
user < operator < admin
```

- **user**: ask, owned conversations, feedback
- **operator**: user capabilities + read-only operations/quality inspection
- **admin**: operator capabilities + sync triggers, quality decisions, API-key user management

OIDC identities are persisted by `(issuer, subject)` so ownership remains stable across token
refreshes. OIDC roles remain IdP-managed; TractusMind can locally disable an external identity but
cannot override its role. `OPS_ADMIN_KEY` remains only as a break-glass admin path.

See [`docs/authenticated-conversations.md`](docs/authenticated-conversations.md).

## Full-corpus validation and quality gate

A benchmark run is valid only after the indexed corpus itself passes consistency and optional
upstream-freshness checks:

```bash
tractusmind-corpus-validate --verify-upstream
```

V1 retrieval/answer datasets cover all six enabled sources: SDK, EDC, Digital Twin Registry,
semantic models, Tractus-X docs, and release metadata.

The full-corpus workflow can refresh every source, validate PostgreSQL/Qdrant/upstream snapshot
identity, run dense/hybrid/rerank/debug evaluation, calibrate the evidence threshold, run answer
safety evaluation and reviewed regressions, then emit a reproducible validation artifact.

The measured threshold is never auto-committed. Human review is required before pinning it in
`config/quality_gate.toml`.

See [`docs/full-corpus-validation.md`](docs/full-corpus-validation.md) and
[`docs/quality-gate.md`](docs/quality-gate.md).

## Human-reviewed quality loop

```text
failed answer / down-vote
          ↓
 pending quality review
          ↓
     human root cause
       /       \
  dismiss    promote
                ↓
         regression case
                ↓
         benchmark export
                ↓
          evaluation gate
```

Raw feedback never becomes gold data automatically.

See [`docs/quality-loop.md`](docs/quality-loop.md).

## Observability

Prometheus captures API/RAG/model/provider/ingestion/worker/quality signals. Grafana ships with
provisioned API/RAG, provider/ingestion, and quality-loop dashboards. Alertmanager evaluates
repository-owned alert rules.

See [`docs/observability.md`](docs/observability.md) and
[`docs/grafana-alerting.md`](docs/grafana-alerting.md).

## Database migrations

Runtime code never creates or alters tables. Current Alembic chain:

```text
0001_core_schema
  -> 0002_user_auth
  -> 0003_oidc_rbac   (head)
```

```bash
tractusmind-db bootstrap
tractusmind-db upgrade
tractusmind-db check
tractusmind-db drift
```

See [`docs/database-migrations.md`](docs/database-migrations.md).

## Current milestone

**V21 — Enterprise OIDC/JWKS + RBAC**

Completed:

- [x] API-key authentication remains backward-compatible
- [x] standard OIDC discovery + JWKS verification
- [x] issuer/expiry/audience/algorithm/signing-key validation
- [x] JWKS caching + forced refresh on unknown signing `kid`
- [x] OIDC provider outage distinguished from invalid bearer token
- [x] stable external identity persistence by `(issuer, subject)`
- [x] `user`, `operator`, and `admin` role hierarchy
- [x] configurable role claim paths for common Keycloak/Entra-style tokens
- [x] read-only operator access to source/run/interaction/quality ops
- [x] admin-only sync, quality decisions, and user lifecycle mutations
- [x] OIDC roles remain identity-provider managed
- [x] local disable state remains authoritative for OIDC users
- [x] `OPS_ADMIN_KEY` retained as break-glass admin access
- [x] request-local auth caching avoids duplicate JWT verification
- [x] `0003_oidc_rbac` migration + schema-head enforcement
- [x] deterministic JWT/RBAC tests with local RSA keys and mocked discovery/JWKS

Still environment/measurement dependent:

- [ ] configure a real enterprise IdP and validate its production token shape
- [ ] execute the first complete V20 full-corpus measurement run
- [ ] review and pin the measured evidence threshold
- [ ] connect the real Alertmanager receiver
- [ ] promote reviewed production cases into committed regressions

Next major milestone: **V22 — Mission Control UI**.

## License

Apache-2.0
