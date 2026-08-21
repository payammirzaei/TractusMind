# 08 — Important Incidents, Root Causes and Engineering Decisions

This document records failures that materially changed the implementation. These are useful because they explain why some parts of TractusMind look more defensive than a typical prototype.

## 1. Frontend dependency security failures

### Symptom

GitHub Actions showed failures in frontend/security checks while the application implementation itself looked healthy.

### Root cause

The frontend was pinned to older React/Next patch versions in a release family with security fixes available.

### Fix

React/ReactDOM and Next.js were moved to patched versions and the resulting dependency graph was verified through npm audit and Trivy.

### Decision

Dependency security is a release gate, not a warning-only report.

---

## 2. OIDC smoke test `localhost` vs `127.0.0.1`

### Symptom

Production build, route smoke and BFF smoke passed, but the OIDC smoke failed on callback return-origin assertion.

### Root cause

The real Next.js callback returned a `localhost` origin while the test fixture required the numerically equivalent `127.0.0.1` origin.

### Fix

The smoke environment was made consistent with the runtime origin.

### Decision

Tests should enforce security semantics, not accidental string differences between equivalent local origins.

---

## 3. Docker BFF smoke could not reach host mock backend

### Symptom

The built Mission Control container started and route smoke passed, but the BFF session smoke returned 503 instead of the expected authentication result.

### Root cause

The container could not reach a mock backend bound only to the GitHub Actions runner loopback.

### Fix

The runtime smoke networking was corrected so the container and mock backend shared a reachable test topology.

### Decision

Container-level tests must model the actual network namespace rather than assuming host loopback is visible from a container.

---

## 4. Compose validation failed because `.env` was absent

### Symptom

Frontend production checks succeeded until the development Compose validation step.

### Root cause

The workflow validated a Compose file that expected `.env`, but CI had not created the example-derived fixture.

### Fix

CI prepares `.env` from the repository example before validating the development topology.

### Decision

Configuration validation should be reproducible from committed examples and should not depend on a developer workstation's hidden files.

---

## 5. Trivy findings came from package managers in the runtime image

### Symptom

Filesystem and backend image scans were clean, while the Mission Control production image still failed Trivy.

### Root cause

The findings came from npm/yarn/corepack tooling inherited into the Node runtime image. Those tools were not required to execute the standalone Next.js server.

### Fix

Unnecessary package-manager tooling was removed from the final runtime image.

### Decision

Prefer removing an unnecessary vulnerable component over adding vulnerability ignores.

---

## 6. Reverse-proxy same-origin requests were rejected

### Symptom

Real full-stack integration rejected a valid browser mutation with 403.

### Root cause

The CSRF/same-origin guard compared browser `Origin` to the internal container `request.url`. Behind Docker/reverse proxy, the browser and internal origins naturally differ.

### Fix

Session and BFF mutation checks were unified around a shared external-origin canonicalization function using forwarded protocol/host or Host. Explicit `Sec-Fetch-Site: cross-site` remains an immediate rejection.

### Decision

Security checks must model the external browser boundary, not internal service addressing. The fix must preserve cross-site rejection rather than weakening the guard.

---

## 7. OIDC frontend/backend configuration mismatch risk

### Symptom/risk

The frontend could theoretically expose SSO while backend OIDC validation remained disabled or incompletely configured.

### Fix

Browser SSO now requires an explicit frontend enable flag, and production Compose maps it from the backend/root `OIDC_ENABLED` switch. The frontend also requires issuer and client ID.

### Decision

Enterprise SSO should fail closed when configuration is incomplete.

---

## 8. Revoked session could linger in the browser

### Symptom/risk

A backend credential rejected with 401/403 could leave the browser's session cookie present until another explicit logout/expiry event.

### Fix

Rejected sessions are expired immediately. Mission Control also periodically revalidates the session and revalidates on window focus.

### Decision

Authorization changes and revoked credentials should converge quickly in the UI without requiring a page refresh.

---

## 9. Full-corpus Tractus-X ingestion caused SIGSEGV (exit 139)

### Symptom

The first self-contained six-source calibration run successfully initialized PostgreSQL, Qdrant and migrations, then crashed during the first source (`tractusx-sdk`) with native exit code 139.

### Investigation

We first isolated dense and sparse FastEmbed paths into separate GitHub Actions jobs. Both succeeded independently, proving that simple model initialization was not the cause.

The investigation then replayed the actual upstream Tractus-X SDK corpus and narrowed the crash to Python source parsing/chunking rather than GitHub access, PostgreSQL, Qdrant or the normal embedding smoke path.

### Root cause

The Python tree-sitter path could hit a native parser/node lifetime crash on a real upstream Python example. Because the failure was native, Python exception handling could not reliably recover from it.

### Fix

Python symbol-aware code chunking was moved to Python's standard-library `ast` implementation. Java/Kotlin/TypeScript/JavaScript continue to use tree-sitter where appropriate, with parser-node handling isolated from long-lived application state.

A regression was added around the complex upstream notification example shape and the exact Tractus-X SDK corpus was revalidated.

### Delivery

The product fix was merged through **PR #11 — `fix: use crash-safe Python AST chunking`** on 2026-08-21.

### Decision

For a language where a robust standard-library parser exists in the same runtime, a safe Python AST path is preferable to retaining a native parser solely for implementation uniformity.

---

## 10. Diagnostic branch proliferation

### Symptom

A large number of `ci/*` branches accumulated while diagnosing workflows.

### Cause

The GitHub connector could inspect pull-request workflow runs more reliably than push-only workflow runs, so temporary PRs were used as observability tools.

### Decision

Diagnostic branches are not product branches. They should be closed/deleted once their evidence has been consumed. Only changes that represent actual product/release behavior should be merged.

At the time this history was written, PR #11 is the merged ingestion fix; corpus-calibration and production-runtime branches remain active validation work, while older diagnostic PRs are disposable.
