# 09 — Current Status and Path to v1.0.0

Snapshot date: **2026-08-21**.

This document distinguishes implementation completeness from release certification. TractusMind's v1 product implementation is effectively complete; the remaining work is evidence, external-provider certification, live deployment, and final repository/release administration.

## Stage 1 — CI and security

**Status: DONE**

Verified durable gates include:

- backend CI/test path,
- frontend dependency audit/typecheck/build,
- production Next.js runtime smoke,
- BFF/session smoke,
- OIDC PKCE smoke,
- production frontend Docker smoke,
- Compose topology validation,
- repository/backend/frontend Trivy scanning.

## Stage 2 — Real full-stack integration

**Status: DONE**

The integration gate exercises PostgreSQL, Redis, Qdrant, migrations, FastAPI, worker, scheduler, Mission Control, readiness, admin bootstrap, HttpOnly session/BFF/RBAC, protected mutations, logout, and service survival.

## Stage 3 — Hardened production runtime

**Status: DONE FOR IMPLEMENTATION / CI EVIDENCE**

PR #12 merged the production-runtime gate and verified the hardened topology end to end with:

- private data services,
- read-only application roots,
- dropped capabilities/no-new-privileges,
- Caddy HTTPS and trusted internal CA,
- Secure `__Host-` session behavior,
- BFF/operator/admin paths,
- explicit cross-site mutation rejection,
- authenticated production smoke,
- clean teardown.

PR #13 then added release preflight, backup/restore proof, release documentation, and fail-fast external-provider smoke requirements.

## Stage 4 — Mission Control product finish

**Status: DONE**

PR #14 merged the premium Mission Control polish while keeping operational data real rather than decorative.

The final v1 visual direction is a modern industrial mission-control system: graphite chassis, recessed evidence wells, tactile controls, status LEDs, compact technical typography, restrained motion, and clear provenance/quality instrumentation.

## Stage 5 — CPU-only production performance

**Status: DONE FOR LOCAL MODEL PATH**

PR #15 introduced a fail-closed CPU performance gate and production telemetry. The benchmark process was constrained to at most two CPUs.

Recorded repeat-gate evidence:

```text
dense p95        51.4 ms   / budget 150 ms
sparse p95        0.32 ms  / budget 10 ms
reranker p95    944 ms     / budget 1650 ms
combined p95    990 ms     / budget 1750 ms
max RSS         893 MiB    / budget 1536 MiB
```

Grafana/Prometheus now expose local-model latency and alerts for sustained dense/reranker regression. This supports a CPU-only Railway v1 query path; a GPU is not required by the measured local retrieval stack.

## Stage 6 — Real-corpus ingestion hardening

**Status: IMPLEMENTATION DONE / FINAL CORPUS CERTIFICATION PENDING**

Real six-source calibration attempts exposed multiple edge cases that synthetic/unit tests did not:

1. Python tree-sitter SIGSEGV on real SDK code → replaced by stdlib AST chunking.
2. Java native-parser risk → deterministic crash-safe Java chunking.
3. legacy semantic-model text containing non-UTF-8 bytes → strict UTF-8 first with controlled CP1252 fallback; binary-looking blobs still fail closed.
4. Turtle files where later prefix declarations could corrupt earlier chunk line ranges → streaming prefix context and regression coverage.

The expensive calibration workflow is now **manual-only** with a larger timeout so normal PR changes do not trigger multi-hour corpus rebuilds.

PR #9 was repurposed from a temporary measurement branch into durable ingestion/calibration hardening and has been merged.

What remains for corpus certification:

1. run the manual six-source calibration once on the final release candidate,
2. confirm all six source syncs complete,
3. validate upstream refs,
4. run retrieval/debug benchmarks,
5. generate the zero-unsafe threshold candidate,
6. human-review and pin `calibration.minimum_relevance_score`,
7. retain the reproducibility manifest as release evidence.

## Stage 7 — Railway live deployment

**Status: RUNBOOK READY / LIVE EVIDENCE PENDING**

The Railway target is documented in `docs/railway-deployment.md`.

Intended production boundary:

```text
Mission Control   public HTTPS
FastAPI           private
PostgreSQL        private/managed
Redis             private/managed
Qdrant            private + persistent
worker            private
scheduler         private
```

The Next.js BFF remains the browser boundary. FastAPI and data services should not receive public domains.

Live deployment still needs real Railway resources, secrets, an LLM provider, and the final hostname/OIDC configuration.

## Stage 8 — External answer certification

**Status: PENDING REAL PROVIDER**

Required certification inputs:

```text
QUALITY_LLM_BASE_URL
QUALITY_LLM_API_KEY
QUALITY_LLM_MODEL
```

The real answer-quality run must verify zero unsafe answer/evidence acceptance, citation validation, claim verification, abstention behavior, and reviewed regressions.

## Stage 9 — Repository/release administration

**Status: PARTIAL**

Current repo state:

- no open PRs before release-status cleanup,
- many historical diagnostic branches still exist,
- `main` branch protection is currently disabled,
- release tagging has not started.

Before `v1.0.0`:

1. enable `main` branch protection with the intended required checks,
2. delete stale merged/diagnostic branches,
3. keep only intentional release work,
4. run release preflight on the exact candidate,
5. tag `v1.0.0`,
6. publish GHCR images/SBOM/provenance,
7. repeat live smoke against the tagged deployment.

## What “100%” means

Feature implementation can be complete before release certification is complete. The final production release requires the whole evidence chain:

```text
CI green
+ security green
+ frontend/full-stack green
+ production-runtime green
+ CPU performance green
+ six-source corpus green
+ calibrated threshold pinned
+ real LLM answer certification green
+ live Railway HTTPS smoke green
+ repository protection/cleanup complete
+ release preflight PASS
= v1.0.0
```

No remaining item should be replaced by a fabricated threshold, fake provider result, or assumed deployment success.
