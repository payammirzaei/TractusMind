# TractusMind v1.0.0 Release Checklist

This checklist is the operator path from release candidate to a tagged `v1.0.0`. A release is not complete because the application builds; every evidence, quality, security, runtime, and deployment gate below must be satisfied.

## 1. Repository state

- [ ] Only intentional release PRs remain open.
- [ ] `main` contains the latest approved production-runtime, security, frontend, and integration changes.
- [ ] CI is green on the exact release candidate commit.
- [ ] Security/Trivy is green on the exact release candidate commit.
- [ ] Frontend build/runtime/BFF/OIDC smoke is green on the exact release candidate commit.
- [ ] Full Stack Integration is green on the exact release candidate commit.
- [ ] Production Runtime is green on the exact release candidate commit.

## 2. Full corpus and retrieval calibration

- [ ] All six enabled Tractus-X sources synchronize successfully into a fresh calibration index.
- [ ] `tractusmind-corpus-validate --verify-upstream` passes.
- [ ] Six-source retrieval benchmark passes.
- [ ] Debug retrieval benchmark passes.
- [ ] Zero-unsafe evidence calibration completes.
- [ ] Calibration artifact and reproducibility manifest are retained.
- [ ] A human reviews the measured candidate threshold.
- [ ] The accepted threshold is committed as `calibration.minimum_relevance_score` in `config/quality_gate.toml`.
- [ ] The pinned value matches the reviewed calibration artifact within `threshold_tolerance`.

## 3. Grounded-answer certification

Configure a real OpenAI-compatible provider for the certification run.

Required values:

```text
QUALITY_LLM_BASE_URL
QUALITY_LLM_API_KEY
QUALITY_LLM_MODEL
```

Then verify:

- [ ] Answer-quality dataset completes against the selected model.
- [ ] Unsafe answer rate is `0.0`.
- [ ] Unsafe evidence-accept rate is `0.0`.
- [ ] Citation validation passes.
- [ ] Atomic claim verification passes required thresholds.
- [ ] Abstention behavior passes insufficient-evidence cases.
- [ ] All reviewed regressions pass.

## 4. Production configuration

- [ ] `.env.production` is created from reviewed deployment values, never committed.
- [ ] Database, Redis, application, OIDC, and observability secrets are injected through the intended secret mechanism.
- [ ] `TRACTUSMIND_DOMAIN` and `ACME_EMAIL` are production values.
- [ ] If OIDC is enabled, the provider uses Authorization Code + PKCE and the exact production callback.
- [ ] `TRACTUSMIND_OIDC_REDIRECT_URI` points to `https://<domain>/api/oidc/callback`.
- [ ] Backend `OIDC_AUDIENCE`, issuer, algorithms, and role claims match the IdP registration.
- [ ] PostgreSQL, Redis, and Qdrant are not host-published.
- [ ] Monitoring endpoints remain operator-only.

Validate the composed topology before starting it:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.ui.prod.yml \
  config >/dev/null
```

## 5. Production deployment and smoke

Start the release candidate:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.ui.prod.yml \
  up -d --build
```

Then verify:

- [ ] Caddy serves valid HTTPS for the real domain.
- [ ] HSTS and browser security headers are present.
- [ ] Nonce-based CSP with `strict-dynamic` reaches the public edge.
- [ ] `/api/health` is healthy.
- [ ] `/api/backend/health/ready` reports PostgreSQL, Redis, and Qdrant healthy.
- [ ] A real API identity can create the Secure HttpOnly Mission Control session.
- [ ] Same-origin authenticated BFF reads work.
- [ ] Authorized admin/operator surfaces work for the intended role.
- [ ] Explicit cross-site mutations are rejected.
- [ ] Logout expires the session.
- [ ] Caddy, frontend, API, worker, scheduler, PostgreSQL, Redis, and Qdrant remain healthy after smoke.

Automated endpoint smoke:

```bash
TRACTUSMIND_PRODUCTION_URL=https://<domain> \
TRACTUSMIND_PRODUCTION_SMOKE_API_KEY=tm_<smoke-key> \
python scripts/production_smoke.py
```

## 6. Operational checks

- [ ] Backup procedure is documented and a PostgreSQL backup can be produced.
- [ ] Restore procedure has been tested on a non-production target.
- [ ] Persistent volumes are confirmed for PostgreSQL and Qdrant.
- [ ] Prometheus is scraping expected production targets.
- [ ] Grafana dashboards load.
- [ ] Alertmanager configuration is valid and the intended delivery route is tested.
- [ ] Logs contain no credentials or bearer tokens during smoke.

## 7. Release preflight

The release must fail closed while any quality calibration value is missing or unsafe contracts drift.

Run:

```bash
python scripts/release_preflight.py
```

Expected result:

```text
TractusMind release preflight: PASS
```

Do not create the release tag unless this command passes on the exact candidate commit.

## 8. Tag and publish

Create only strict semantic release tags:

```bash
git tag -a v1.0.0 -m "TractusMind v1.0.0"
git push origin v1.0.0
```

The release workflow then independently verifies:

1. the tag format is `vMAJOR.MINOR.PATCH`,
2. the tagged commit belongs to `main`,
3. release preflight passes,
4. only then are backend and Mission Control images built and pushed.

Expected images:

```text
ghcr.io/payammirzaei/tractusmind:v1.0.0
ghcr.io/payammirzaei/tractusmind-ui:v1.0.0
```

Both release images are multi-architecture (`linux/amd64`, `linux/arm64`) and are published with SBOM and provenance attestations.

## 9. Post-release verification

- [ ] Pull the exact `v1.0.0` images from GHCR on a clean target.
- [ ] Confirm image digests are recorded with the release notes.
- [ ] Re-run production endpoint smoke against the deployed release images.
- [ ] Confirm no unexpected open PR/diagnostic branch is required for production state.
- [ ] Update `CHANGELOG.md` from `[Unreleased]` to `[1.0.0]` with the release date.
- [ ] Publish the final demo screenshots/video and architecture diagram.

Only after these checks is TractusMind `v1.0.0` considered production-released.
