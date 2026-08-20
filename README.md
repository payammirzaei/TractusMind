# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem — with an inspectable Mission Control UI.**

TractusMind answers architecture, documentation, coding, debugging, semantic-model, and version-specific questions from traceable Tractus-X sources. It is designed around provenance, retrieval quality, measurable evaluation, operational safety, and inspectability rather than opaque AI behavior.

## Mission Control

The V22 control surface lives in `frontend/` and uses **Next.js 16.3 + React 19.2 + Tailwind CSS 4.3 + shadcn-compatible components + Motion**.

Its visual language is modern industrial skeuomorphism: graphite chassis, recessed evidence wells, tactile controls, status LEDs, and restrained cyan/amber instrumentation. Chat content stays comparatively flat for readability.

Functional consoles:

- **Copilot** — grounded chat, citation markers, feedback, route/verification metadata
- **Evidence Inspector** — repo, ref, snapshot commit, content commit, file/lines, retrieval/rerank/debug scores
- **Sources** — source registry, snapshot state, file counts, admin sync controls
- **Operations** — ingestion summary and run channel
- **Quality** — human review queue and regression status
- **Access** — API-key identity provisioning and enable/disable controls

Navigation is RBAC-aware: `user < operator < admin`.

## Core backend

- FastAPI grounded answer API
- allowlisted, commit-pinned Tractus-X GitHub ingestion
- structure-aware Markdown/code/YAML/Turtle chunking
- Qdrant dense + BM25 hybrid retrieval
- exact debug retrieval lane + RRF fusion
- cross-encoder reranking
- deterministic source/version/ref/commit routing
- OpenAI-compatible grounded generation
- backend-owned citations + atomic claim verification
- bounded provider retries, idempotency, and circuit breakers
- incremental PostgreSQL/Qdrant synchronization
- Redis + Dramatiq background ingestion
- persisted conversations, traces, feedback, and human quality review
- API-key identities + enterprise OIDC/JWKS
- user/operator/admin RBAC
- Alembic migrations + ORM drift checks
- six-source full-corpus validation + calibration workflow
- production quality gate + reviewed regressions
- Prometheus/OpenTelemetry/Grafana/Alertmanager observability
- hardened production Compose + Caddy TLS + Docker secrets
- Trivy security CI + GHCR images with SBOM/provenance

## Grounded answer pipeline

```text
question
  -> bounded owned history when eligible
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

History is context, not evidence. Previous assistant answers cannot become source citations. Explicit `ref:` and `commit:` constraints fail closed when indexed provenance is unavailable.

## Local development

Backend only:

```bash
cp .env.example .env
docker compose up --build
```

Backend + Mission Control:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.ui.yml \
  up --build
```

```text
Mission Control http://localhost:3100
API             http://localhost:8000
OpenAPI         http://localhost:8000/docs
Grafana         http://localhost:3000
Prometheus      http://localhost:9090
Alertmanager    http://localhost:9093
Qdrant          http://localhost:6333/dashboard
```

Frontend only:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

## Mission Control security boundary

The browser does **not** keep the bearer credential in localStorage. `/api/session` validates it against backend `/v1/me` and stores it in an HttpOnly, SameSite cookie. Browser requests then use the Next.js BFF endpoint `/api/backend/*`, which proxies only allowlisted `v1` and `health` backend paths.

This keeps the FastAPI service private in the production UI topology while preserving the existing API-key and OIDC/JWKS authentication model.

See [`docs/mission-control.md`](docs/mission-control.md).

## Authentication and RBAC

```text
Authorization: Bearer tm_...
             or
Authorization: Bearer <OIDC JWT>
```

OIDC uses discovery + JWKS and validates issuer, expiry, configured audience, asymmetric signing algorithm, and signing key. Unknown `kid` values trigger one JWKS refresh for normal key rotation.

Roles:

```text
user < operator < admin
```

- **user** — ask, owned conversations, feedback
- **operator** — user capabilities + read-only operations/quality inspection
- **admin** — operator capabilities + sync, quality decisions, identity lifecycle

OIDC identities are persisted by `(issuer, subject)`. OIDC roles stay IdP-managed; TractusMind can locally disable an external identity but does not override its role. `OPS_ADMIN_KEY` remains only as break-glass admin access.

## Full-corpus validation

A benchmark run is valid only after the indexed corpus passes consistency and optional upstream-freshness checks:

```bash
tractusmind-corpus-validate --verify-upstream
```

V1 retrieval/answer datasets cover all six enabled sources: SDK, EDC, Digital Twin Registry, semantic models, Tractus-X docs, and release metadata.

The measured evidence threshold is never auto-committed. Human review is required before pinning it in `config/quality_gate.toml`.

See [`docs/full-corpus-validation.md`](docs/full-corpus-validation.md) and [`docs/quality-gate.md`](docs/quality-gate.md).

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

## Production deployment

Backend production topology remains in `docker-compose.prod.yml`. Mission Control is added through `docker-compose.ui.prod.yml`; Caddy becomes the sole public edge and proxies to the frontend, while the frontend reaches FastAPI only over the private backend network.

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.ui.prod.yml \
  up -d --build
```

PostgreSQL, Redis, and Qdrant remain private. Grafana/Prometheus/Alertmanager remain operator-only loopback services.

See [`docs/production-deployment.md`](docs/production-deployment.md) and [`docs/mission-control.md`](docs/mission-control.md).

## Validation gates

Backend CI validates Ruff, migrations/drift, PostgreSQL-backed tests, Compose/Prometheus/Grafana configuration and security checks.

Frontend CI validates:

1. production dependency audit at HIGH severity,
2. TypeScript typecheck,
3. Next.js production build,
4. runtime Docker image build.

## Current milestone

**V22 — Mission Control UI**

Implemented in the current cut:

- [x] Next.js/Tailwind/shadcn/Motion foundation
- [x] industrial skeuomorphic design system
- [x] HttpOnly BFF authentication boundary
- [x] role-aware navigation
- [x] grounded chat workbench
- [x] source/provenance inspector
- [x] route + claim-verification visibility
- [x] feedback wired to backend quality loop
- [x] source registry + admin sync
- [x] ingestion operations console
- [x] quality review console
- [x] user/API-key administration
- [x] dedicated frontend CI/build/security gate
- [x] dev and production Compose overlays
- [x] Caddy-to-Mission-Control production edge

Still environment-dependent rather than missing backend/UI code:

- [ ] run the first complete V20 full-corpus measurement and pin the reviewed threshold
- [ ] validate a production Keycloak/Entra token shape
- [ ] connect the real Alertmanager receiver
- [ ] run the V22 frontend Actions build on the deployment environment and fix any platform-specific issue it exposes

## License

Apache-2.0
