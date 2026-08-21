# TractusMind v1.0.0 Release Checklist

This is the operator path from the current feature-complete implementation to a tagged `v1.0.0`. A release is not complete merely because the code builds; calibration, answer quality, live deployment, and release evidence must all be real.

## Current snapshot — 2026-08-21

Already implemented and merged:

- [x] backend/general CI
- [x] frontend build/runtime/BFF/OIDC smoke
- [x] Security/Trivy for repository + backend + Mission Control images
- [x] Full Stack Integration
- [x] hardened Production Runtime HTTPS gate
- [x] release preflight and fail-closed image publishing
- [x] PostgreSQL backup/restore smoke
- [x] premium Mission Control polish
- [x] CPU-only retrieval-model performance gate
- [x] Grafana local-model p95 telemetry and performance alerts
- [x] crash-safe Python/Java ingestion fixes
- [x] legacy semantic-model text decoding fix
- [x] Turtle line-provenance fix
- [x] Railway deployment runbook
- [x] expensive full-corpus calibration changed to manual-only

Still required before the release tag:

- [ ] final six-source calibration on the exact release candidate
- [ ] human-reviewed threshold pin
- [ ] real-LLM grounded-answer certification
- [ ] live Railway deployment smoke
- [ ] `main` branch protection
- [ ] stale diagnostic branch deletion
- [ ] release preflight PASS on the exact candidate
- [ ] `v1.0.0` tag + GHCR publication

## 1. Repository state

- [ ] No unintended PR remains open.
- [ ] `main` contains all reviewed release work.
- [ ] CI is green on the exact release candidate commit.
- [ ] Security/Trivy is green on the exact release candidate commit.
- [ ] Frontend build/runtime/BFF/OIDC smoke is green on the exact release candidate commit.
- [ ] Full Stack Integration is green on the exact release candidate commit.
- [ ] Production Runtime is green on the exact release candidate commit.
- [ ] CPU Performance is green on the exact release candidate commit if model/runtime code changed since the last certified measurement.
- [ ] `main` branch protection requires the intended release checks.
- [ ] Stale diagnostic branches are deleted after their evidence is no longer needed.

## 2. Final full-corpus calibration

The workflow is manual-only by design because a fresh six-source rebuild can take hours.

Run it once on the final candidate and verify:

- [ ] all six enabled Tractus-X sources synchronize into a fresh index,
- [ ] `tractusmind-corpus-validate --verify-upstream` passes,
- [ ] six-source retrieval benchmark passes,
- [ ] debug retrieval benchmark passes,
- [ ] zero-unsafe evidence calibration completes,
- [ ] artifact + reproducibility manifest are retained,
- [ ] a human reviews the candidate threshold,
- [ ] accepted threshold is committed as `calibration.minimum_relevance_score` in `config/quality_gate.toml`,
- [ ] pinned value matches the reviewed artifact within `threshold_tolerance`.

Do not invent or preselect the threshold.

## 3. Grounded-answer certification

Configure the real OpenAI-compatible provider:

```text
QUALITY_LLM_BASE_URL
QUALITY_LLM_API_KEY
QUALITY_LLM_MODEL
```

Then verify:

- [ ] answer-quality dataset completes against the selected model,
- [ ] unsafe answer rate is `0.0`,
- [ ] unsafe evidence-accept rate is `0.0`,
- [ ] citation validation passes,
- [ ] atomic claim verification meets required thresholds,
- [ ] insufficient-evidence cases abstain correctly,
- [ ] all reviewed regressions pass.

## 4. Railway production configuration

Use [`railway-deployment.md`](railway-deployment.md) as the target deployment runbook. The self-hosted Compose profile remains a hardened reference under [`production-deployment.md`](production-deployment.md).

Target Railway boundary:

```text
Mission Control   public
FastAPI           private
PostgreSQL        private/managed
Redis             private/managed
Qdrant            private + persistent
worker            private
scheduler         private
```

Before deployment:

- [ ] create managed PostgreSQL and Redis,
- [ ] create private Qdrant with persistent storage,
- [ ] configure API/worker/scheduler variables without committing secrets,
- [ ] configure Mission Control BFF to `http://api.railway.internal:8000`,
- [ ] use `/health/ready` for API deployment readiness,
- [ ] use `/api/health` for Mission Control health,
- [ ] run Alembic migration as the single pre-deploy migration writer,
- [ ] expose a public domain only for Mission Control,
- [ ] configure OIDC only after the final callback hostname is known.

Do not weaken the non-root runtime merely to persist the model cache.

## 5. Live production smoke

On the actual Railway HTTPS hostname verify:

- [ ] Mission Control loads successfully,
- [ ] BFF reaches the private FastAPI service,
- [ ] PostgreSQL, Redis, and Qdrant are healthy through `/health/ready`,
- [ ] a real identity can create the Secure HttpOnly session,
- [ ] same-origin authenticated BFF reads work,
- [ ] authorized operator/admin surfaces work,
- [ ] explicit cross-site mutations are rejected,
- [ ] logout expires the session,
- [ ] Copilot returns grounded output with citations/evidence inspection,
- [ ] browser CSP/HSTS/security headers are correct on the Railway edge,
- [ ] local-model telemetry is visible,
- [ ] live latency is compatible with the CPU performance budget,
- [ ] no backend/data service is unintentionally public.

## 6. Operational proof

- [x] backup procedure exists,
- [x] restore procedure is exercised in CI,
- [ ] production PostgreSQL backup can be produced,
- [ ] Qdrant persistence/rebuild procedure is verified for the deployed target,
- [ ] Prometheus/monitoring receives expected runtime signals or an equivalent production monitor is configured,
- [ ] intended alert route is tested,
- [ ] logs contain no credentials or bearer tokens during smoke.

## 7. Release preflight

Run on the exact release candidate:

```bash
python scripts/release_preflight.py
```

Required result:

```text
TractusMind release preflight: PASS
```

The command must remain fail-closed while the calibration threshold is missing or unsafe contracts drift.

## 8. Tag and publish

Only after every blocking item above is complete:

```bash
git tag -a v1.0.0 -m "TractusMind v1.0.0"
git push origin v1.0.0
```

The release workflow verifies tag format, ancestry from `main`, and release preflight before image publication.

Expected images:

```text
ghcr.io/payammirzaei/tractusmind:v1.0.0
ghcr.io/payammirzaei/tractusmind-ui:v1.0.0
```

Release images are multi-architecture (`linux/amd64`, `linux/arm64`) with SBOM and provenance attestations.

## 9. Post-release verification

- [ ] record published image digests,
- [ ] re-run live smoke against the exact tagged release,
- [ ] update `CHANGELOG.md` from `[Unreleased]` to `[1.0.0]` with release date,
- [ ] publish final screenshots/demo/architecture evidence,
- [ ] confirm no temporary diagnostic branch is required for production state.

Only after these checks is TractusMind `v1.0.0` production-released.
