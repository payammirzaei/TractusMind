# 06 — CI, Security and Full-Stack Integration

## Why CI became a project stage of its own

The project reached a point where individual features were mostly complete, but “it builds on my machine” was not enough. We therefore treated CI verification as a dedicated release stage.

The target became:

```text
CI/test + Frontend/build + Security/Trivy + Full Stack Integration
```

A stage was not considered complete until GitHub Actions itself reported the relevant gates green.

## Backend CI

Backend CI validates the Python application through the repository's normal test/lint/migration flow.

Key areas include:

- Ruff lint/format expectations,
- Python tests,
- database schema/migration behavior,
- service-level regressions.

## Frontend CI

The frontend workflow matured into a production-runtime verification path rather than only `npm run build`.

It currently covers:

- install,
- npm vulnerability audit,
- TypeScript checking,
- production build,
- production Next.js runtime startup,
- route smoke,
- BFF/session smoke,
- OIDC PKCE smoke,
- OIDC-disabled fail-closed smoke,
- production Docker image build/start,
- smoke against the built image,
- development and production Compose topology validation.

## React/Next security dependency incident

The green-CI pass identified security risk in the frontend dependency line. We updated the runtime from the vulnerable older React/Next patch versions to patched versions and verified the result through both npm audit and Trivy.

Important lesson: dependency scanning was treated as part of release correctness, not an optional report.

## Production runtime image hardening

Trivy later showed findings from package-management tooling inside the frontend runtime image rather than from TractusMind application code.

Because npm/yarn/corepack are not needed to run the final standalone Next.js server, they were removed from the production runtime image instead of suppressing the vulnerabilities.

This reduced both CVE exposure and attack surface.

## Security workflow

Security CI scans:

- repository filesystem/dependencies,
- backend image,
- Mission Control image,
- secret/misconfiguration classes supported by the configured scanner.

The policy is to fail on relevant fixed HIGH/CRITICAL findings.

## First real green gate

The frontend/security diagnostic work produced a fully green candidate with:

- CI/test ✅
- Frontend/build ✅
- Security/Trivy ✅

That validated the first major completion stage.

## Full-stack integration gate

The next step was to prove the actual service topology rather than independent applications.

A GitHub Actions gate was added that boots real services with Docker Compose:

```text
Mission Control
  -> BFF
  -> FastAPI
  -> PostgreSQL
  -> Redis
  -> Qdrant
  -> worker
  -> scheduler
```

The test performs real migrations and real authentication/bootstrap behavior.

It verifies:

- PostgreSQL readiness,
- Redis readiness,
- Qdrant readiness,
- migration completion,
- FastAPI health,
- worker/scheduler startup,
- Mission Control startup,
- backend readiness through the BFF,
- real admin identity bootstrap,
- HttpOnly session creation,
- authenticated BFF access,
- admin mutation,
- explicit cross-site mutation rejection,
- logout/session expiry,
- long-running service survival after the smoke sequence.

## Reverse-proxy origin bug exposed by integration

The integration gate caught a bug unit tests had not exposed.

The original mutation guard effectively compared browser `Origin` against the server's internal `request.url` origin. Inside Docker/reverse proxy topology this could mean:

```text
browser origin: http://localhost:3100
internal request origin: http://frontend:3000
```

A valid same-origin browser request was therefore rejected.

The fix introduced shared external-origin canonicalization using trusted forwarded protocol/host or Host, while preserving immediate rejection of `Sec-Fetch-Site: cross-site` requests.

This was an important architectural improvement because the security model now matches real proxy deployment semantics instead of only direct development access.

## Full-stack completion result

After the origin/network fixtures were corrected, the real full-stack gate passed. At that point the project had evidence that the core control plane works as one system rather than a collection of independently green services.

## Diagnostic branches and PRs

Several temporary PRs were intentionally created to expose GitHub Actions logs for push workflows or to isolate a failing subsystem. They were not product branches and were closed after their evidence was collected.

Examples include:

- frontend/security green-gate diagnostics,
- full-stack gate revisions,
- quality-environment probes,
- proxy-origin verification,
- embedding/native-crash isolation.

The principle is:

> Diagnostic branches are disposable evidence-generating tools. Product fixes should land on `main` through the appropriate verified change.

## Current expected release gates

Before v1, the final release candidate should have green evidence for:

- backend CI,
- frontend CI,
- security scans,
- real full-stack integration,
- full-corpus calibration,
- real LLM answer certification,
- hardened production-runtime smoke,
- live HTTPS deployment smoke.
