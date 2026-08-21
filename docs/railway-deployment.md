# Railway production deployment runbook

This runbook adapts the hardened TractusMind production architecture to Railway without pretending
that Docker Compose networking, host-mounted secrets, or the Caddy edge exist unchanged on the
platform. The self-hosted topology remains documented in `docs/production-deployment.md`.

Railway-specific behavior should be rechecked against the current Railway documentation before a
live release because platform semantics can change.

## Target topology

```text
Internet
   |
   | Railway HTTPS / custom domain
   v
Mission Control (Next.js)  [public]
   |
   | BFF only, Railway private network
   v
FastAPI API                [private]
   |        |        |
   |        |        +------> external LLM provider
   |        |
   |        +---------------> Qdrant [private + persistent volume]
   |
   +---- PostgreSQL [managed/private]
   +---- Redis      [managed/private]

Ingestion worker            [private/no domain]
   |---- PostgreSQL / Redis / Qdrant
   +---- GitHub provider egress

Scheduler                   [private/no domain]
   +---- Redis / control data
```

The browser should not receive a backend bearer token and should not call FastAPI directly. Keep the
existing Mission Control BFF/session boundary: only the Next.js service needs public networking;
FastAPI, Redis, PostgreSQL, Qdrant, worker, and scheduler stay private.

Railway private service DNS uses `<service-name>.railway.internal`. Unlike Docker Compose, there is
no host port-mapping layer on private networking: connect to the port the destination process
actually listens on.

## Services

### `frontend`

Source: this repository with root directory `frontend/` and `frontend/Dockerfile`.

- public networking: enabled
- healthcheck path: `/api/health`
- expected container port: `3000` unless Railway overrides `PORT`
- backend URL: `http://api.railway.internal:8000`
- custom domain: add only after the Railway-provided domain passes smoke tests

Required runtime configuration includes:

```text
TRACTUSMIND_API_URL=http://api.railway.internal:8000
TRACTUSMIND_OIDC_ENABLED=false|true
TRACTUSMIND_OIDC_ISSUER_URL=...
TRACTUSMIND_OIDC_CLIENT_ID=...
TRACTUSMIND_OIDC_SCOPES=openid profile email
TRACTUSMIND_OIDC_REDIRECT_URI=https://<public-domain>/api/oidc/callback
```

Do not configure the OIDC redirect URI until the final public hostname is known.

### `api`

Source: repository root using the root `Dockerfile`.

- public networking: disabled
- process port: `8000`
- healthcheck path: `/health/ready`
- one Uvicorn process for the v1 CPU profile
- baseline resource target: 2 CPU and 4 GiB memory when the selected Railway plan supports it

The CPU-only release gate is documented in `docs/cpu-performance.md`. On the certified two-CPU
workload, local model compute is well inside the pinned release budget; a GPU is not a v1
requirement.

Railway performs deployment healthchecks from `healthcheck.railway.app`. Include that hostname in
`TRUSTED_HOSTS` together with the private API hostname used by internal callers. Railway healthchecks
protect deployment activation but are not continuous uptime monitoring; retain Prometheus/alerts or
another continuous monitor for runtime operations.

### `worker`

Source: repository root using the same backend image/Dockerfile as the API, with the start command
overridden to the production ingestion worker command:

```bash
dramatiq app.workers.tasks --processes 1 --threads 1
```

Keep it private and do not generate a domain. The worker owns expensive source synchronization and
corpus embedding so full ingestion cannot block the API process.

### `scheduler`

Source: repository root using the backend image with start command:

```bash
tractusmind-scheduler
```

Keep it private and do not generate a domain.

### PostgreSQL and Redis

Prefer Railway managed PostgreSQL and Redis rather than reproducing the Compose database containers.
Use Railway reference variables so application connection variables follow the managed service
credentials instead of copying hostnames/passwords manually.

TractusMind expects an async SQLAlchemy PostgreSQL URL and a Redis URL. Validate the exact supplied
Railway variables before mapping them; do not commit credentials or resolved connection strings.

### Qdrant

Deploy the pinned Qdrant image line validated by the repository, currently `qdrant/qdrant:v1.19.0`,
as a private Railway service. Attach a Railway volume at the Qdrant storage path used by the image
(`/qdrant/storage`) and expose no public domain.

Application services connect privately, for example:

```text
QDRANT_URL=http://qdrant.railway.internal:6333
```

Qdrant persistence and PostgreSQL backups must still be treated as one recovery set. If Qdrant is
lost, rebuild it from the immutable allowlisted Git snapshots before serving grounded answers.

## Model cache decision

The self-hosted Compose profile mounts `/home/app/.cache` into the non-root API and worker
containers. Railway volumes are mounted with root ownership, and Railway documents a root-runtime
compatibility switch for non-root images. Do **not** enable a root runtime merely to preserve the
FastEmbed cache: the hardened TractusMind backend intentionally runs as a non-root user.

For the first Railway deployment, keep the model cache ephemeral unless a non-root writable volume
strategy is proven in a staging environment. A clean deployment may therefore redownload model
artifacts before first use. The local model initialization itself is measured by the CPU performance
gate; network download time is separate.

If repeated download/cold-start time becomes material, prefer baking reviewed model assets into the
container image during build over weakening the runtime user. Re-run Security/Trivy and CPU
Performance after any such image change.

## Database migration

Use Railway's pre-deploy command on the API release to apply the schema before the new API becomes
active:

```bash
alembic upgrade head
```

The API also checks database revision during startup and fails closed on a stale schema. Do not run
multiple independent migration writers during the same release.

## Variables and secrets

Railway variables replace the self-hosted `secrets/` bind mounts. At minimum, resolve these groups
without placing secret values in source control:

```text
# Core storage
DATABASE_URL=...
REDIS_URL=...
QDRANT_URL=http://qdrant.railway.internal:6333
QDRANT_COLLECTION=tractusmind_chunks

# Providers
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=...
GITHUB_TOKEN=...

# Security/runtime
ENV=production
TRUSTED_HOSTS=api.railway.internal,healthcheck.railway.app
API_DOCS_ENABLED=false
OIDC_ENABLED=false|true
OIDC_ISSUER_URL=...
OIDC_AUDIENCE=...
OIDC_OPERATOR_ROLES=...
OIDC_ADMIN_ROLES=...

# Mission Control
TRACTUSMIND_API_URL=http://api.railway.internal:8000
TRACTUSMIND_OIDC_ENABLED=false|true
TRACTUSMIND_OIDC_ISSUER_URL=...
TRACTUSMIND_OIDC_CLIENT_ID=...
TRACTUSMIND_OIDC_REDIRECT_URI=https://<public-domain>/api/oidc/callback
```

Use the current `.env.production.example` and application settings as the authoritative variable
inventory. The list above is a deployment map, not a replacement for configuration validation.

## Networking rules

1. Generate a public domain only for Mission Control.
2. Keep API, Qdrant, worker, scheduler, PostgreSQL, and Redis on Railway private networking.
3. Point Mission Control's server-side BFF at `api.railway.internal:8000`.
4. Do not expose Qdrant, Redis, PostgreSQL, Prometheus, or Alertmanager to the public internet.
5. Do not carry Caddy into the Railway profile merely to mimic Compose. Railway terminates the
   public HTTPS edge; application CSP/security headers remain the application's responsibility.
6. Before release, verify HSTS and all browser security headers on the actual Railway/custom-domain
   response, because the self-hosted Caddy header layer is absent.

## Health and deployment behavior

Configure:

```text
frontend healthcheck: /api/health
api healthcheck:      /health/ready
```

`/health/ready` checks PostgreSQL, Redis, and Qdrant, making it appropriate for deployment
activation. A successful Railway deployment healthcheck is not proof of continuous health after the
deployment becomes active; production alerting remains required.

If a Railway service has an attached volume, current Railway behavior can introduce a short redeploy
downtime because old and new deployments cannot mount the same volume simultaneously. This matters
most for the Qdrant service; normal application deployments should not require a Qdrant redeploy.

## Staging sequence

1. create managed PostgreSQL and Redis
2. create private Qdrant and attach its persistent volume
3. deploy API privately and map storage/provider variables
4. run `alembic upgrade head` as the pre-deploy migration
5. configure API `/health/ready`
6. deploy worker and scheduler privately
7. deploy Mission Control with `TRACTUSMIND_API_URL` pointing to private API DNS
8. configure Mission Control `/api/health`
9. generate the temporary Railway frontend domain
10. smoke session creation, BFF auth, Copilot, citations, evidence inspector, Sources/Ops/Quality,
    admin mutation, and logout
11. enable/configure OIDC only after the callback hostname is final
12. add the custom domain and repeat HTTPS/security-header/OIDC smoke
13. run a live end-to-end latency sample; compare local-model telemetry with the certified CPU gate
14. verify backup and recovery procedures before tagging the release

## Release evidence required

Do not call the Railway deployment release-certified until all of these are recorded:

- `/health/ready` is green through the deployed path
- Mission Control BFF can reach the private API without public API exposure
- Secure session cookie and CSRF rejection work on the final HTTPS hostname
- OIDC works with the real issuer if enabled
- real LLM provider passes the Quality Gate
- full-corpus calibration threshold is pinned
- live latency is compatible with the CPU performance budget
- PostgreSQL backup/restore proof remains green
- Qdrant persistence/rebuild procedure is verified
- browser CSP/HSTS/security headers are correct without the self-hosted Caddy edge

## Railway references

Current Railway documentation used when writing this runbook:

- https://docs.railway.com/guides/docker-compose
- https://docs.railway.com/deployments/healthchecks
- https://docs.railway.com/networking/private-networking
- https://docs.railway.com/volumes
- https://docs.railway.com/deployments

These links are operational references only. Repository tests, measured artifacts, and the actual
staging deployment remain the release evidence.
