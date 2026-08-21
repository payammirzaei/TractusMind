# 10 — Chronological Milestone Log

This is a development-history summary, not a replacement for `git log`. It groups the architectural milestones that materially changed TractusMind.

## Phase A — Source-grounded backend foundation

The project established FastAPI, PostgreSQL, Qdrant, GitHub source discovery/fetching, a curated source registry, document normalization, chunking, dense indexing, and retrieval. The early invariant was that repository/ref/snapshot provenance must survive all the way to answer citations.

## Phase B — Hybrid retrieval and evidence control

The retrieval path gained BM25 sparse vectors, hybrid dense+sparse search, exact/debug retrieval, RRF fusion, cross-encoder reranking, source/ref/snapshot filtering, evidence thresholding, and abstention.

## Phase C — Grounded answer and verification

Generation added bounded grounded context, citation construction/validation, atomic claim verification, structured answer metadata, and the rule: **history is context, never evidence**.

## Phase D — Stateful conversations and quality loop

The backend added owned conversations/messages, API-key identities, RBAC, feedback persistence, human quality review, regression promotion, and evaluation/quality-gate tooling.

## Phase E — Background operations and production backend

Operational work added Redis, Dramatiq workers, scheduler, incremental synchronization, ingestion state, provider retries/circuit breaking, Prometheus/OpenTelemetry, Grafana/Alertmanager, production Compose, startup migrations, Docker secrets, and backup/restore procedures.

## Phase F — Enterprise authentication

Authentication expanded from local API keys to external OIDC identities. The browser layer adopted Authorization Code + PKCE plus a Next.js BFF/session boundary so backend bearer credentials are not persisted in browser storage.

## Phase G — Mission Control

Mission Control grew into a complete engineering console with live readiness, Copilot, evidence/claim inspection, Sources, Ops, Quality, Admin, global command launcher, Command Center, responsive states, live session revalidation, and SSO-first login when configured.

## Phase H — Frontend security and runtime CI

The frontend workflow began testing the production artifact, not just source code: dependency audit, typecheck, production build, BFF/session smoke, mock OIDC/PKCE, disabled-SSO fail-closed behavior, Docker runtime smoke, browser security headers, and Compose validation.

## Phase I — Green CI milestone

**PR #1 — frontend/security green gate — merged**

Frontend/build and Security/Trivy reached green after root-cause dependency/runtime fixes.

## Phase J — Full-stack integration

Temporary diagnostic PRs exposed networking, environment-fixture, and reverse-proxy origin/CSRF assumptions. The durable Full Stack Integration gate then exercised Mission Control → BFF → FastAPI → PostgreSQL/Redis/Qdrant with worker/scheduler and RBAC.

## Phase K — Self-contained quality infrastructure

GitHub Actions gained isolated PostgreSQL/Qdrant state and built-in GitHub-token access for public Tractus-X sources. This made full-corpus measurement reproducible rather than dependent on a developer machine.

## Phase L — Native ingestion crash discovery

The first real-corpus calibration attempt reached `tractusx-sdk` and exposed a native SIGSEGV in Python tree-sitter chunking.

**PR #10 — embedding/native diagnostic — closed, not merged**

Dense and sparse model initialization were isolated and passed, narrowing the fault away from embeddings.

**PR #11 — crash-safe Python AST chunking — merged**

Python symbol chunking moved to the standard-library AST path. Java later moved to a deterministic crash-safe chunking path as well.

## Phase M — Hardened production runtime

**PR #12 — production runtime gate — merged**

The real hardened Compose topology was proven end to end: private data services, read-only application roots, dropped capabilities, Caddy HTTPS, trusted internal CA, real admin provisioning, Secure `__Host-` session behavior, cross-site mutation rejection, BFF/operator/admin paths, and teardown.

## Phase N — Release engineering hardening

**PR #13 — release preflight hardening — merged**

Added fail-closed release/tag preflight, backup/restore CI proof, release checklist/changelog support, provider preflight smoke, and guarded multi-architecture GHCR publication with SBOM/provenance.

## Phase O — Mission Control premium polish

**PR #14 — premium Mission Control polish — merged**

The frontend visual system converged on a modern industrial mission-control language: graphite chassis, recessed evidence wells, tactile controls, status LEDs, technical typography, restrained animations, and consistent control-plane surfaces without fake telemetry.

## Phase P — CPU-only production performance

**PR #15 — CPU retrieval performance gate — merged**

A two-CPU evidence-first benchmark measured dense/sparse/reranker/combined local model compute and RSS. Only after measurement were fail-closed budgets pinned.

Recorded repeat-gate evidence:

```text
dense p95        51.4 ms   / budget 150 ms
sparse p95        0.32 ms  / budget 10 ms
reranker p95    944 ms     / budget 1650 ms
combined p95    990 ms     / budget 1750 ms
max RSS         893 MiB    / budget 1536 MiB
```

Grafana/Prometheus local-model p95 telemetry and sustained-regression alerts were added. The measured v1 query path does not require a GPU.

## Phase Q — Railway production adaptation

A Railway-specific runbook was added instead of pretending the self-hosted Caddy/Compose topology maps one-to-one onto Railway.

The intended platform boundary is public Mission Control with a private BFF-to-FastAPI path and private PostgreSQL/Redis/Qdrant/worker/scheduler services.

## Phase R — Real semantic-model corpus edge cases

A later full-corpus attempt proved the earlier Python/Java fixes, then exposed two new real-data issues:

1. legacy semantic-model text that was not strict UTF-8,
2. Turtle prefix declarations that could make an earlier statement inherit a later prefix line and produce invalid `end_line < start_line` provenance.

Durable fixes were added:

- UTF-8 remains authoritative, with controlled CP1252 fallback for legacy text and fail-closed binary detection,
- Turtle prefix context is now streaming/position-aware so line provenance remains valid,
- regression tests cover both behaviors.

The same attempt also showed that a clean serial six-source rebuild can exceed two hours. The full calibration workflow was therefore changed to **manual-only** with a larger timeout so normal PR work does not repeatedly consume multi-hour runners.

**PR #9 — full-corpus ingestion/calibration hardening — merged**

The PR was renamed/reframed before merge because the durable product value was ingestion hardening and manual release calibration, not a successfully completed threshold certification.

## Current PR snapshot

| PR | Purpose | Final status | Durable product merge? |
| --- | --- | --- | --- |
| #1 | Frontend/security green gate | merged | yes |
| #2/#3/#5/#7 | Full-stack diagnostics | closed | no |
| #4/#8 | Quality environment diagnostics | closed | no |
| #6 | stale release diagnostic | closed/stale historical | no |
| #9 | Corpus ingestion + manual calibration hardening | merged | yes |
| #10 | Native embedding/parser diagnostic | closed | no |
| #11 | Crash-safe Python AST chunking | merged | yes |
| #12 | Hardened production runtime gate | merged | yes |
| #13 | Release preflight + backup/restore hardening | merged | yes |
| #14 | Mission Control premium polish | merged | yes |
| #15 | CPU-only performance gate | merged | yes |

## Next milestones that still need real evidence

1. manual six-source calibration completes on the final release candidate,
2. measured threshold is human-reviewed and pinned,
3. real LLM grounded-answer certification passes,
4. Railway deployment passes live HTTPS/session/BFF/security/latency smoke,
5. `main` branch protection is enabled and stale diagnostic branches are deleted,
6. release preflight passes on the exact candidate,
7. `v1.0.0` is tagged and published.
