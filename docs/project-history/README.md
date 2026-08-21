# TractusMind Project History

This directory records how TractusMind evolved from a source-grounded RAG backend into a production-oriented engineering copilot with Mission Control, hardened runtime gates, measurable retrieval quality, and release engineering.

The feature documents under `docs/` explain **how the current system works**. This history explains **what was built, why architectural decisions changed, which incidents exposed real weaknesses, what was verified, and what remains before `v1.0.0`**.

## Documents

1. [Project overview and goals](./01-project-overview.md)
2. [Backend and RAG architecture evolution](./02-backend-rag-architecture.md)
3. [Knowledge ingestion and retrieval pipeline](./03-ingestion-and-retrieval.md)
4. [Conversations, authentication, RBAC, feedback and quality](./04-auth-conversations-quality.md)
5. [Mission Control frontend evolution](./05-mission-control-frontend.md)
6. [CI, security and full-stack integration](./06-ci-security-integration.md)
7. [Production, observability and release engineering](./07-production-and-operations.md)
8. [Important incidents, root causes and engineering fixes](./08-incidents-and-decisions.md)
9. [Current status and path to v1.0.0](./09-current-status-and-roadmap.md)
10. [Chronological milestone log](./10-milestone-log.md)

## Current high-level state

Snapshot: **2026-08-21, after PR #9 hardening merge**.

- Core backend/RAG implementation: **feature-complete for v1**.
- Mission Control: **feature-complete and premium-polished for v1**.
- CI, frontend runtime, Security/Trivy, Full Stack Integration: **verified green**.
- Hardened Production Runtime HTTPS gate: **merged and verified green** through PR #12.
- Release preflight + backup/restore hardening: **merged** through PR #13.
- Premium Mission Control visual polish: **merged** through PR #14.
- CPU-only retrieval-model performance gate: **merged and measured** through PR #15; two-CPU combined local-model p95 was ~0.99s with ~893 MiB max RSS on the recorded run.
- Railway production topology/runbook: **documented**.
- Real-corpus ingestion hardening: **merged**; Python native parsing crash, Java crash risk, legacy semantic-model decoding and Turtle line provenance all have durable fixes/regressions.
- Full-corpus calibration workflow: **manual-only** so normal changes do not spend hours rebuilding the corpus.
- Final six-source calibration + measured threshold pin: **still required release evidence**.
- Real LLM grounded-answer certification: **still requires provider inputs**.
- Live Railway HTTPS smoke: **still requires an actual deployment**.
- `main` branch protection and stale branch deletion: **still repository-admin cleanup**.
- Final `v1.0.0` release: **not yet tagged**.

## Canonical current documentation

- [`../architecture.md`](../architecture.md)
- [`../mission-control.md`](../mission-control.md)
- [`../full-corpus-validation.md`](../full-corpus-validation.md)
- [`../quality-gate.md`](../quality-gate.md)
- [`../cpu-performance.md`](../cpu-performance.md)
- [`../production-deployment.md`](../production-deployment.md)
- [`../railway-deployment.md`](../railway-deployment.md)
- [`../release-checklist.md`](../release-checklist.md)

## Guiding engineering principles

- **Source grounding before fluent generation.** Conversation history may provide context, but it must never become evidence.
- **Fail closed on provenance.** Explicit repository/ref/commit constraints are not silently relaxed.
- **No fake operational data.** Mission Control status, quality data and provenance come from real backend state.
- **Browser credentials stay server-side.** Bearer/API credentials are converted into HttpOnly sessions through the BFF boundary.
- **Security findings are fixed at the root where practical.** Unnecessary/vulnerable runtime tooling is removed rather than hidden behind ignores.
- **Quality thresholds are measured, not invented.** The production evidence threshold comes from full-corpus calibration evidence and human review.
- **Performance budgets are measured, not guessed.** CPU model budgets were pinned only after a real constrained benchmark.
- **A feature is not done merely because it builds.** The target is reproducible behavior under CI, Docker and production-like runtime gates.
- **Platform adaptation must preserve security boundaries.** Railway uses its own HTTPS/private-network semantics rather than copying the self-hosted Caddy/Compose topology blindly.
