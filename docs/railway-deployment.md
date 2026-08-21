# Railway production deployment runbook

This runbook adapts the hardened TractusMind production architecture to Railway without pretending Docker Compose networking, host-mounted secrets, or the Caddy edge exist unchanged on the platform. The self-hosted topology remains documented in `docs/production-deployment.md`.

Railway platform behavior should be rechecked against current Railway documentation before the live release.

## Target topology

```text
Internet
   |
Railway HTTPS / custom domain
   |
Mission Control (Next.js)  [public]
   |
   | BFF only over Railway private network
   v
FastAPI API                [private]
   |        |        |
   |        |        +------> external LLM provider
   |        +---------------> Qdrant [private + persistent]
   +------------------------> PostgreSQL [managed/private]
   +------------------------> Redis [managed/private]

Ingestion worker           [private/no domain]
Scheduler                  [private/no domain]
```

The browser never needs a direct FastAPI URL or backend bearer token. Only Mission Control receives public networking.

Railway private DNS uses `<service-name>.railway.internal`.

## Config as code

Repository-backed services have reviewed Railway config files under [`../deploy/railway/`](../deploy/railway/README.md):

| Service | Root Directory | Config File |
| --- | --- | --- |
| `frontend` | `/frontend` | `/deploy/railway/frontend.railway.json` |
| `api` | `/` | `/deploy/railway/api.railway.json` |
| `worker` | `/` | `/deploy/railway/worker.railway.json` |
| `scheduler` | `/` | `/deploy/railway/scheduler.railway.json` |

Railway's Config File path is repository-absolute and does not follow Root Directory. Configure both values explicitly in each service.

The files pin Dockerfile builds, watch paths, start commands, healthchecks where applicable, restart behavior, and the single API pre-deploy migration/bootstrap command. Secrets and managed-service references stay in Railway variables.

## Services

### `frontend`

- source root: `/frontend`
- config: `/deploy/railway/frontend.railway.json`
- public networking: enabled
- healthcheck: `/api/health`
- backend URL: `http://api.railway.internal:8000`
- add the final custom domain only after the temporary Railway domain passes smoke

Runtime variables:

```text
TRACTUSMIND_API_URL=http://api.railway.internal:8000
TRACTUSMIND_OIDC_ENABLED=false|true
TRACTUSMIND_OIDC_ISSUER_URL=...
TRACTUSMIND_OIDC_CLIENT_ID=...
TRACTUSMIND_OIDC_SCOPES=openid profile email
TRACTUSMIND_OIDC_REDIRECT_URI=https://<public-domain>/api/oidc/callback
```

Do not finalize the OIDC redirect URI before the final public hostname is known.

### `api`

- source root: `/`
- config: `/deploy/railway/api.railway.json`
- public networking: disabled
- healthcheck: `/health/ready`
- one Uvicorn process for the v1 CPU profile
- baseline target: 2 CPU / 4 GiB memory when the Railway plan supports it

The start command uses Railway's injected `PORT` with `8000` as fallback. The API config runs `tractusmind-db bootstrap` as the only pre-deploy migration writer.

The CPU-only gate in `docs/cpu-performance.md` demonstrates that the local retrieval-model query path fits the pinned two-CPU budget; a GPU is not required for v1.

Include `api.railway.internal` and Railway's healthcheck host in `TRUSTED_HOSTS`.

### `worker`

- source root: `/`
- config: `/deploy/railway/worker.railway.json`
- public networking: disabled
- one Dramatiq process / one thread for the v1 baseline

The worker owns expensive ingestion and embedding work so source synchronization cannot block the API process. Do not run the multi-hour release calibration as a worker startup task.

### `scheduler`

- source root: `/`
- config: `/deploy/railway/scheduler.railway.json`
- public networking: disabled
- start command: `tractusmind-scheduler`

### PostgreSQL and Redis

Prefer Railway managed PostgreSQL and Redis. Use Railway reference variables rather than copying resolved hostnames/passwords into source control.

TractusMind accepts ordinary `postgresql://` URLs and converts them to the async SQLAlchemy driver form internally when needed.

### Qdrant

Deploy the validated image line:

```text
qdrant/qdrant:v1.19.0
```

Keep it private, attach persistent storage at `/qdrant/storage`, and connect from application services with:

```text
QDRANT_URL=http://qdrant.railway.internal:6333
```

PostgreSQL and Qdrant remain one logical recovery set. If Qdrant is lost, rebuild its corpus from the immutable allowlisted Git snapshots before serving grounded answers.

## Variables and secrets

Railway variables replace the self-hosted `secrets/` bind mounts. Use the current application settings and `.env.production.example` as the authoritative inventory.

Core API mapping:

```text
APP_ENV=production
DATABASE_URL=...
REDIS_URL=...
QDRANT_URL=http://qdrant.railway.internal:6333
QDRANT_COLLECTION=tractusmind_chunks
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=...
OPS_ADMIN_KEY=...
METRICS_ADMIN_KEY=...
TRUSTED_HOSTS=api.railway.internal,healthcheck.railway.app
DOCS_ENABLED=false
TRUST_FORWARDED_FOR=true
OIDC_ENABLED=false|true
OIDC_ISSUER_URL=...
OIDC_AUDIENCE=...
OIDC_ALLOWED_ALGORITHMS=RS256
OIDC_OPERATOR_ROLES=...
OIDC_ADMIN_ROLES=...
```

Worker additionally needs `GITHUB_TOKEN` and the Dramatiq Prometheus temp-directory variables documented in `deploy/railway/README.md`.

Never commit secret values or resolved managed-service credentials.

## Database migration

The API Railway config uses the same repository-owned bootstrap path as the hardened production topology:

```text
tractusmind-db bootstrap
```

Railway pre-deploy commands run before the new deployment becomes active. If the command exits non-zero, deployment must stop. Worker and scheduler do not run migrations independently.

The API also checks database revision during startup and fails closed on stale schema.

## Model cache decision

The backend image intentionally runs non-root. Railway volumes can introduce root-ownership friction for non-root containers; do **not** set `RAILWAY_RUN_UID=0` merely to persist the FastEmbed cache.

For the first deployment, keep model cache ephemeral. A clean deployment may redownload model artifacts before first use; that network download time is distinct from the measured local model compute budget.

If cold downloads become operationally significant, prefer baking reviewed model assets into the image and then re-run Security and CPU Performance gates.

## Networking rules

1. Generate a public domain only for Mission Control.
2. Keep API, Qdrant, worker, scheduler, PostgreSQL, and Redis private.
3. Point the server-side BFF at `http://api.railway.internal:8000`.
4. Do not expose data stores or internal observability endpoints publicly.
5. Do not carry Caddy into Railway merely to mimic Compose; Railway owns the public HTTPS edge.
6. Re-verify CSP, HSTS and security headers on the actual Railway/custom-domain response because the self-hosted Caddy header layer is absent.

## Health behavior

```text
frontend: /api/health
api:      /health/ready
```

`/health/ready` checks PostgreSQL, Redis and Qdrant and is appropriate for deployment activation. Railway deployment healthchecks are not a substitute for continuous runtime monitoring.

A volume-backed Qdrant redeploy may have different availability characteristics from stateless app redeploys; normal frontend/API changes should not require redeploying Qdrant.

## Staging sequence

1. create a Railway project/environment,
2. add managed PostgreSQL and Redis,
3. add private Qdrant and attach `/qdrant/storage`,
4. create `api`, `worker`, `scheduler`, and `frontend` from this GitHub repository,
5. set Root Directory + Config File for each service from the table above,
6. wire API storage/provider/security variables,
7. deploy API and confirm the pre-deploy bootstrap succeeds,
8. wait for API `/health/ready`,
9. deploy worker and scheduler,
10. wire frontend variables to private API DNS,
11. deploy frontend and generate a temporary Railway domain,
12. smoke session creation, BFF auth, Copilot, citations/evidence, Sources/Ops/Quality, admin mutation and logout,
13. configure OIDC only after the callback hostname is final,
14. add the final custom domain and repeat HTTPS/security-header/OIDC smoke,
15. run a live latency sample and compare local-model telemetry with the certified CPU gate,
16. verify backup/recovery behavior before the release tag.

## Release evidence required

Do not call the Railway deployment release-certified until all of these are recorded:

- `/health/ready` is green on the deployed API,
- Mission Control BFF reaches FastAPI over private networking,
- no backend/data service has an unintended public domain,
- Secure session cookie and cross-site mutation rejection work on final HTTPS,
- OIDC works with the real issuer if enabled,
- the real LLM provider passes the Quality Gate,
- full-corpus calibration threshold is pinned,
- live latency remains compatible with CPU budgets,
- PostgreSQL backup/recovery is verified,
- Qdrant persistence/rebuild behavior is verified,
- browser CSP/HSTS/security headers are correct on Railway's edge.

## Railway references

Current Railway documentation used for this profile:

- https://docs.railway.com/config-as-code
- https://docs.railway.com/config-as-code/reference
- https://docs.railway.com/deployments/monorepo
- https://docs.railway.com/deployments/pre-deploy-command
- https://docs.railway.com/deployments/healthchecks
- https://docs.railway.com/networking/private-networking
- https://docs.railway.com/volumes

Repository tests, measured artifacts, and the actual staging deployment remain the release evidence.
