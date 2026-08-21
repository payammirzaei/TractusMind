# 09 — Current Status and Path to v1.0.0

Snapshot date: **2026-08-21**.

This document is the release-oriented view of the project. It intentionally distinguishes “implemented” from “verified” and “still requires external evidence.”

## Stage 1 — Green CI and security

**Status: DONE**

Verified work includes:

- backend CI/test path,
- frontend install/audit/typecheck/build,
- production Next.js runtime smoke,
- BFF/session smoke,
- OIDC PKCE smoke,
- OIDC-disabled fail-closed smoke,
- production frontend Docker image smoke,
- Compose topology validation,
- repository/backend/frontend Trivy security scanning.

Important security fixes completed during this stage:

- patched React/Next dependency line,
- removal of unnecessary npm/yarn/corepack tooling from the production UI image,
- session rejection expiry,
- explicit browser-SSO enable/fail-closed behavior.

## Stage 2 — Real full-stack integration

**Status: DONE**

A GitHub Actions integration gate has successfully exercised the real control plane with:

- PostgreSQL,
- Redis,
- Qdrant,
- migrations,
- FastAPI,
- worker,
- scheduler,
- Mission Control,
- BFF readiness,
- real admin bootstrap,
- HttpOnly session,
- authenticated operator/admin endpoints,
- protected mutation behavior,
- logout,
- service survival.

The reverse-proxy origin/CSRF bug discovered by this gate was fixed without weakening explicit cross-site rejection.

## Stage 3 — Full corpus and calibration

**Status: ACTIVE / NOT YET CERTIFIED**

Completed infrastructure:

- ephemeral PostgreSQL in GitHub Actions,
- ephemeral Qdrant,
- built-in GitHub Actions token for public Tractus-X source access,
- clean database bootstrap,
- six-source synchronization workflow,
- corpus/ref validation steps,
- retrieval benchmark steps,
- debug benchmark steps,
- zero-unsafe threshold candidate generation,
- calibration artifact/reproducibility manifest output.

Important blocker that was discovered and fixed:

- real `tractusx-sdk` ingestion triggered native SIGSEGV during Python code parsing,
- dense/sparse embedding paths were isolated and verified independently,
- root cause was narrowed to Python tree-sitter parsing,
- Python code chunking moved to standard-library AST,
- regression coverage was added,
- fix merged via PR #11.

What remains for this stage:

1. rerun the full six-source calibration on the latest `main`,
2. confirm all source syncs complete,
3. run retrieval and debug benchmarks,
4. generate the measured threshold candidate,
5. review and pin the final production threshold,
6. keep the calibration manifest as release evidence.

PR #9 remains a temporary calibration/measurement branch and should not be treated as product code merely because it exists.

## Stage 4 — Hardened production runtime

**Status: ACTIVE**

The repository already contains the hardened production Compose architecture, Docker secrets model, Caddy edge, private data services, health/readiness endpoints, observability stack, backup/restore scripts and production smoke client.

PR #12 is active validation work for a production-runtime gate that exercises the hardened topology end to end with local/internal HTTPS.

Before considering this stage complete:

1. rebase/update the gate against current `main` if required,
2. obtain green CI/security/runtime evidence,
3. merge only the durable production-gate changes,
4. remove temporary diagnostic-only artifacts/branches.

## Stage 5 — External answer certification and live release

**Status: NOT YET COMPLETE**

These steps require real external inputs and therefore must not be faked in CI:

### Real LLM answer certification

Provide an OpenAI-compatible provider configuration:

- LLM base URL,
- API key,
- model identifier.

Then run grounded answer evaluation against the calibrated six-source corpus and verify citation/claim/abstention behavior.

### Real HTTPS deployment

Deploy reviewed images to the actual target host/domain and verify:

- DNS/TLS,
- production secrets,
- backend readiness,
- Mission Control health,
- authenticated browser session,
- core routes and operator/admin surfaces,
- security headers,
- monitoring,
- backup procedure.

Run the production smoke client against the real HTTPS endpoint.

### Final release

After all gates are green:

- clean temporary CI branches,
- update final README/docs/screenshots/demo references,
- verify changelog/release notes,
- verify backend and Mission Control release images,
- confirm SBOM/provenance output,
- tag and publish **`v1.0.0`**.

## Repository hygiene items before v1

These are release-hardening tasks rather than core product features:

- delete stale diagnostic `ci/*` branches after evidence is consumed,
- close obsolete diagnostic PRs,
- consider enabling `main` branch protection with required release checks,
- keep production secrets and `.env.production` outside Git,
- ensure the final production OIDC redirect URI/domain is explicit when OIDC is enabled.

## What “100%” means from here

The software implementation is already in the final phase. The remaining work is primarily **certification and deployment evidence**.

TractusMind should only be called 100% / v1-ready when the following chain is true at the same time:

```text
CI green
+ security green
+ full-stack green
+ six-source corpus green
+ calibrated threshold pinned
+ real LLM answer quality green
+ hardened production runtime green
+ live HTTPS smoke green
+ release artifacts/docs complete
= v1.0.0
```
