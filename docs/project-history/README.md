# TractusMind Project History

This directory records how TractusMind evolved from an initial source-grounded RAG backend into a production-oriented engineering copilot with a full Mission Control UI, hardened deployment topology, quality gates, and end-to-end CI verification.

It is intentionally different from the feature-specific documents under `docs/`. The existing documents explain **how the current system works**. This folder explains **what we built, why we built it, what decisions changed along the way, what was verified, and what still remains before v1.0.0**.

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

As of 2026-08-21:

- Core backend architecture: complete.
- Mission Control application: functionally complete for v1.
- CI, frontend build, security scanning and real full-stack integration: verified green.
- Tractus-X SDK ingestion SIGSEGV: root-caused to Python tree-sitter parsing and fixed by moving Python code chunking to the standard-library AST path; the fix was merged through PR #11.
- Full-corpus calibration: active validation work remains.
- Hardened production-runtime gate: active validation work remains through PR #12.
- Live LLM answer certification and final public production smoke still require real provider/deployment inputs.
- Final `v1.0.0` release has not yet been tagged.

## Canonical technical documentation

For the exact current implementation, use these documents together with this history:

- [`../architecture.md`](../architecture.md)
- [`../mission-control.md`](../mission-control.md)
- [`../full-corpus-validation.md`](../full-corpus-validation.md)
- [`../quality-gate.md`](../quality-gate.md)
- [`../production-deployment.md`](../production-deployment.md)
- [`../observability.md`](../observability.md)
- [`../operations.md`](../operations.md)

## Guiding engineering principles

The project consistently converged on a small set of rules:

- **Source grounding before fluent generation.** Conversation history may provide context, but it must never become evidence.
- **Fail closed on provenance.** Explicit repository/ref/commit constraints are not silently relaxed.
- **No fake operational data.** Mission Control status, quality data and provenance must come from real backend state.
- **Browser credentials stay server-side.** Bearer/API credentials are converted into HttpOnly sessions through the BFF boundary rather than persisted in browser storage.
- **Security findings are fixed at the root where practical.** Vulnerable or unnecessary runtime tooling is removed instead of hidden behind ignores.
- **Quality thresholds are measured, not invented.** Retrieval/abstention thresholds are expected to come from full-corpus calibration evidence.
- **A feature is not considered done merely because it builds.** The target is reproducible end-to-end behavior under Docker, CI and production-like conditions.
