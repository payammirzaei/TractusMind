# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem — with an inspectable Mission Control UI.**

TractusMind answers architecture, documentation, coding, debugging, semantic-model, and version-specific questions from traceable Tractus-X sources. The system is designed around provenance, measurable retrieval quality, fail-closed evidence handling, operational safety, and inspectability rather than opaque AI behavior.

> **Release status:** the v1 implementation is feature-complete. Remaining work is release certification and live deployment evidence: one final six-source calibration, threshold pinning, real-LLM answer certification, live Railway smoke, repository protection/branch cleanup, and the `v1.0.0` tag.

## Mission Control

The production UI lives in `frontend/` and uses **Next.js 16.3 + React 19.2 + Tailwind CSS 4.3 + shadcn-compatible components + Motion**.

Its visual language is a modern industrial mission-control system: graphite chassis, recessed evidence wells, tactile controls, status LEDs, restrained cyan/amber instrumentation, and compact technical typography.

Main surfaces:

- **Copilot** — grounded chat, citations, feedback, routing/evidence/verification metadata
- **Command Center** — readiness, source/ingestion/quality state, topology and live operations
- **Evidence Inspector** — repo, ref, snapshot commit, content commit, file/lines, retrieval/rerank/debug scores
- **Sources** — registry, snapshot state, file counts, admin sync controls
- **Operations** — ingestion summaries, runs and errors
- **Quality** — human review queue and regression status
- **Admin** — API-key identity provisioning, role and lifecycle controls

Navigation is RBAC-aware: `user < operator < admin`.

## Core backend

- FastAPI grounded answer API
- allowlisted, commit-pinned Tractus-X GitHub ingestion
- Markdown/code/YAML/Turtle chunking with crash-safe Python and Java paths
- Qdrant dense + BM25 hybrid retrieval
- exact debug retrieval lane + RRF fusion
- cross-encoder reranking
- deterministic source/version/ref/commit routing
- OpenAI-compatible grounded generation
- backend-owned citations + atomic claim verification
- abstention when evidence is insufficient
- incremental PostgreSQL/Qdrant synchronization
- Redis + Dramatiq background ingestion
- persisted conversations, traces, feedback, and human quality review
- API-key identities + enterprise OIDC/JWKS
- user/operator/admin RBAC
- Alembic migrations + ORM drift checks
- six-source corpus validation + manual release calibration workflow
- Prometheus/OpenTelemetry/Grafana/Alertmanager observability
- hardened production Compose + Caddy reference topology
- Railway production runbook
- Trivy security CI + GHCR release images with SBOM/provenance

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

History is context, never evidence. Previous assistant answers cannot become source citations. Explicit `ref:` and `commit:` constraints fail closed when indexed provenance is unavailable.

## Authentication and browser security

The browser does **not** keep backend bearer credentials in localStorage. Mission Control creates an HttpOnly session through `/api/session` and accesses FastAPI through the allowlisted Next.js BFF path `/api/backend/*`.

Production behavior includes:

- Secure `__Host-` session cookie
- SameSite session protection
- explicit cross-site mutation rejection
- per-request nonce CSP with `strict-dynamic`
- OIDC Authorization Code + PKCE when enabled
- backend JWT issuer/audience/signature validation
- periodic session revalidation and immediate expiry of rejected sessions

See [`docs/mission-control.md`](docs/mission-control.md).

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

## CPU-only production profile

A dedicated CI gate measures the local retrieval-model path with the benchmark process constrained to at most two CPUs.

Latest certified two-CPU evidence before release cleanup:

```text
dense p95        51.4 ms   / budget 150 ms
sparse p95        0.32 ms  / budget 10 ms
reranker p95    944 ms     / budget 1650 ms
combined p95    990 ms     / budget 1750 ms
max RSS         893 MiB    / budget 1536 MiB
```

The gate is fail-closed, and production Prometheus/Grafana expose local-model latency with alerts for sustained dense/reranker regressions. A GPU is not required for the v1 query path.

See [`docs/cpu-performance.md`](docs/cpu-performance.md).

## Full-corpus calibration

The release calibration covers all six enabled Tractus-X sources: SDK, EDC, Digital Twin Registry, semantic models, Tractus-X docs, and release metadata.

The workflow is intentionally **manual-only** because a clean six-source rebuild can take hours. It validates the corpus and upstream refs, runs retrieval/debug benchmarks, measures the zero-unsafe evidence threshold, and produces reproducibility artifacts.

Real corpus runs exposed and led to durable fixes for:

- Python tree-sitter native SIGSEGV → replaced with stdlib AST chunking
- Java parser crash risk → deterministic crash-safe Java chunking
- legacy semantic-model text encoding → UTF-8 first with controlled CP1252 fallback
- Turtle prefix/line provenance edge case → streaming prefix context with valid line ranges

The measured evidence threshold is never auto-committed. Human review is required before pinning `calibration.minimum_relevance_score` in `config/quality_gate.toml`.

See [`docs/full-corpus-validation.md`](docs/full-corpus-validation.md) and [`docs/quality-gate.md`](docs/quality-gate.md).

## Production deployment

Two production paths are documented:

- **Self-hosted hardened Compose:** [`docs/production-deployment.md`](docs/production-deployment.md)
- **Railway target topology:** [`docs/railway-deployment.md`](docs/railway-deployment.md)

For Railway, the intended v1 topology is:

```text
Internet
   |
Railway HTTPS
   |
Mission Control (public)
   |
private BFF -> FastAPI
                |-- PostgreSQL
                |-- Redis
                |-- Qdrant
                |-- external LLM

worker + scheduler remain private
```

Only Mission Control should receive a public domain. FastAPI, Qdrant, PostgreSQL, Redis, worker and scheduler remain private.

## Verified release engineering

Durable gates already merged into `main`:

- [x] backend/general CI
- [x] frontend production build/runtime/BFF/OIDC smoke
- [x] Trivy repository + backend + Mission Control image scanning
- [x] real Full Stack Integration gate
- [x] hardened Production Runtime HTTPS gate
- [x] release preflight that blocks unsafe/unpinned releases
- [x] PostgreSQL backup/restore smoke
- [x] CPU-only performance budget gate
- [x] Grafana local-model p95 telemetry + performance alerts
- [x] premium Mission Control UI polish
- [x] crash-safe real-corpus ingestion fixes
- [x] Railway deployment runbook

## Remaining path to `v1.0.0`

1. run the **manual six-source calibration** once on the final candidate,
2. review and pin the measured evidence threshold,
3. run grounded-answer certification against the selected real OpenAI-compatible LLM,
4. deploy to Railway and pass live HTTPS/session/BFF/health/security-header smoke,
5. enable `main` branch protection and remove stale diagnostic branches,
6. run `python scripts/release_preflight.py` on the exact candidate,
7. tag and publish **`v1.0.0`**.

For the detailed release checklist see [`docs/release-checklist.md`](docs/release-checklist.md). For the historical engineering record see [`docs/project-history/`](docs/project-history/).

## License

Apache-2.0
