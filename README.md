# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem — with an inspectable Mission Control UI.**

TractusMind answers architecture, documentation, coding, debugging, semantic-model, and version-specific questions from traceable Tractus-X sources. It is designed around provenance, retrieval quality, measurable evaluation, operational safety, and inspectability rather than opaque AI behavior.

> **Project journey:** [`docs/project-history/`](docs/project-history/) documents what has been built, the architectural decisions, incidents/root causes, CI milestones, production work, and the exact remaining path to `v1.0.0`.

## Mission Control

The V23 Mission Control surface lives in `frontend/` and uses **Next.js 16.3 + React 19.2 + Tailwind CSS 4.3 + shadcn-compatible components + Motion**.

Its visual language is modern industrial skeuomorphism: graphite chassis, recessed evidence wells, tactile controls, status LEDs, and restrained cyan/amber instrumentation. Chat content stays comparatively flat for readability.

Functional consoles:

- **Copilot** — grounded chat, citations, feedback, routing/evidence/verification metadata
- **Command Center** — live readiness, source/ingestion/quality state and system topology
- **Evidence Inspector** — repo, ref, snapshot commit, content commit, file/lines, retrieval/rerank/debug scores
- **Sources** — source registry, snapshot state, file counts, admin sync controls
- **Operations** — ingestion summary, runs and errors
- **Quality** — human review queue and regression status
- **Admin** — API-key identity provisioning, role and lifecycle controls

Navigation is RBAC-aware: `user < operator < admin`.

## Core backend

- FastAPI grounded answer API
- allowlisted, commit-pinned Tractus-X GitHub ingestion
- structure-aware Markdown/code/YAML/Turtle chunking with crash-safe Python/Java paths
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

The browser does **not** keep the bearer credential in localStorage. `/api/session` validates it against backend `/v1/me` and stores it in an HttpOnly, SameSite cookie. Browser requests then use the Next.js BFF endpoint `/api/backend/*`, which proxies only allowlisted backend paths and methods.

Production uses a Secure `__Host-` session cookie. Rejected/revoked backend sessions are expired immediately, and Mission Control revalidates active sessions periodically and on browser focus.

HTML responses use a per-request nonce CSP with `strict-dynamic`; production does not rely on `unsafe-inline` for script execution. Caddy preserves the application CSP and adds the public-edge HSTS policy.

Browser SSO uses **Authorization Code + PKCE** as a public client. No frontend client secret is required. SSO fails closed unless explicitly enabled and fully configured.

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

The hardened Production Runtime gate now proves the composed topology end to end in CI: private service exposure, read-only application roots, Caddy HTTPS, certificate verification, real admin provisioning, Mission Control session/BFF/RBAC behavior, and clean teardown.

See [`docs/production-deployment.md`](docs/production-deployment.md) and [`docs/mission-control.md`](docs/mission-control.md).

## Validation gates

The repository uses multiple independent release gates.

Backend/general CI validates linting, migrations/schema behavior, PostgreSQL-backed tests and configuration correctness.

Frontend CI validates:

1. dependency audit,
2. TypeScript typecheck,
3. Next.js production build,
4. production route/BFF/OIDC smokes,
5. production Docker image startup and smoke,
6. development/production Compose topology.

Security CI scans the repository plus backend and Mission Control container images with Trivy.

A real **Full Stack Integration** gate boots PostgreSQL, Redis, Qdrant, migrations, FastAPI, worker, scheduler and Mission Control together, then exercises readiness, admin bootstrap, HttpOnly session/BFF/RBAC, protected mutations and logout.

A separate **Production Runtime** gate proves the hardened HTTPS deployment topology rather than only validating Compose syntax.

## Current milestone

**V23 — Mission Control + v1 production hardening**

Implemented and verified:

- [x] source-grounded backend/RAG pipeline
- [x] incremental six-source ingestion architecture
- [x] grounded citations + claim verification
- [x] conversations, feedback and quality review loop
- [x] API-key + OIDC/JWKS authentication
- [x] Next.js Mission Control and Command Center
- [x] HttpOnly BFF authentication boundary
- [x] enterprise browser SSO with Authorization Code + PKCE
- [x] role-aware Sources/Ops/Quality/Admin consoles
- [x] per-request nonce CSP + browser-policy smoke
- [x] frontend production runtime smoke suite
- [x] Trivy security gates
- [x] real full-stack Docker integration gate
- [x] hardened production Compose architecture
- [x] hardened production runtime HTTPS gate
- [x] Tractus-X SDK Python-ingestion SIGSEGV root cause and AST-based fix
- [x] crash-safe Java ingestion path for EDC/Digital Twin corpus sources

Remaining certification/release work:

- [ ] complete the six-source corpus calibration run
- [ ] review and pin the measured evidence threshold
- [ ] run grounded-answer certification against a real OpenAI-compatible LLM
- [ ] merge the reviewed calibration candidate
- [ ] deploy to the real HTTPS target and pass production smoke
- [ ] publish/tag `v1.0.0`

For the detailed history and exact status, start at [`docs/project-history/README.md`](docs/project-history/README.md).

## License

Apache-2.0
