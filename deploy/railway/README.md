# Railway service configuration

These files are the config-as-code layer for the TractusMind Railway deployment. They intentionally cover build/deploy behavior only; secrets, managed-service references, public domains, and resource sizing remain Railway project settings.

Railway allows each service to use a custom config file by absolute repository path. The config file path is independent of the service Root Directory.

## Service map

| Railway service | Source root | Config file | Public network | Notes |
| --- | --- | --- | --- | --- |
| `frontend` | `/frontend` | `/deploy/railway/frontend.railway.json` | yes | only public application service |
| `api` | `/` | `/deploy/railway/api.railway.json` | no | runs DB bootstrap as pre-deploy command |
| `worker` | `/` | `/deploy/railway/worker.railway.json` | no | one Dramatiq process / one thread for v1 |
| `scheduler` | `/` | `/deploy/railway/scheduler.railway.json` | no | control-plane scheduler only |
| PostgreSQL | Railway managed | n/a | no | reference its connection variables |
| Redis | Railway managed | n/a | no | reference its connection variables |
| Qdrant | image `qdrant/qdrant:v1.19.0` | n/a | no | attach persistent volume at `/qdrant/storage` |

## Dashboard wiring

For each repository-backed service:

1. connect `payammirzaei/TractusMind`,
2. set the Root Directory from the table above,
3. set **Config File** to the absolute path from the table,
4. keep the service on Railway private networking,
5. generate a public domain only for `frontend`.

The frontend BFF should use:

```text
TRACTUSMIND_API_URL=http://api.railway.internal:8000
```

The API should use private managed-service references for PostgreSQL/Redis and:

```text
QDRANT_URL=http://qdrant.railway.internal:6333
QDRANT_COLLECTION=tractusmind_chunks
```

## API variables

Resolve values through Railway variables/reference variables; do not commit secrets.

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
OIDC_OPERATOR_ROLES=...
OIDC_ADMIN_ROLES=...
```

Use the application settings and `.env.production.example` as the authoritative variable inventory.

## Worker variables

Use the same storage connection values as the API plus GitHub provider access:

```text
APP_ENV=production
DATABASE_URL=...
REDIS_URL=...
QDRANT_URL=http://qdrant.railway.internal:6333
QDRANT_COLLECTION=tractusmind_chunks
GITHUB_TOKEN=...
PROMETHEUS_MULTIPROC_DIR=/tmp/dramatiq-prometheus
prometheus_multiproc_dir=/tmp/dramatiq-prometheus
dramatiq_prom_db=/tmp/dramatiq-prometheus
```

Do not run full-corpus calibration as part of deployment startup. Normal source synchronization belongs to the worker; the expensive release calibration remains a manual GitHub Actions certification gate.

## Scheduler variables

```text
APP_ENV=production
REDIS_URL=...
```

## Frontend variables

```text
TRACTUSMIND_API_URL=http://api.railway.internal:8000
TRACTUSMIND_OIDC_ENABLED=false|true
TRACTUSMIND_OIDC_ISSUER_URL=...
TRACTUSMIND_OIDC_CLIENT_ID=...
TRACTUSMIND_OIDC_SCOPES=openid profile email
TRACTUSMIND_OIDC_REDIRECT_URI=https://<final-public-domain>/api/oidc/callback
```

Do not configure the final OIDC redirect until the public hostname is fixed.

## Migration behavior

Only the `api` config declares a pre-deploy migration/bootstrap command:

```text
tractusmind-db bootstrap
```

It runs before the new API deployment is activated. Worker and scheduler must not independently race the migration writer.

## Model cache

Keep the FastEmbed model cache ephemeral for the first Railway deployment. The backend image intentionally runs non-root; do not use `RAILWAY_RUN_UID=0` merely to make a root-owned Railway volume writable.

If cold-download time becomes material, prefer a reviewed image-build strategy for model assets, then re-run Security and CPU Performance gates.

## Before the first live deploy

- create PostgreSQL and Redis managed services,
- create private Qdrant + persistent volume,
- create the four repository-backed services,
- apply Root Directory + Config File paths,
- wire reference variables/secrets,
- confirm no public domain exists for API/data/worker/scheduler,
- deploy API and wait for `/health/ready`,
- deploy worker + scheduler,
- deploy frontend and generate a temporary Railway domain,
- smoke session/BFF/Copilot/evidence/admin/logout,
- add the final domain/OIDC settings only after the temporary-domain smoke is clean.

For the full deployment/security sequence see [`../../docs/railway-deployment.md`](../../docs/railway-deployment.md).
