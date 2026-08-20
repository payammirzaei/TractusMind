# Production deployment and security

V19 separates local development from a hardened self-hosted production topology.

## Production topology

```text
Internet
   |
   | 443/tcp + 443/udp only
   v
 Caddy (automatic TLS)
   |
   v
 FastAPI API ------------------> provider egress (LLM)
   |
   +---------------- private backend ----------------+
   |             |             |          |          |
PostgreSQL     Redis         Qdrant    Prometheus  Grafana
                              ^            |
                              |        Alertmanager
                    Worker ---+
                      |
                      +------------------> provider egress (GitHub)
```

PostgreSQL, Redis, and Qdrant have no host-published ports. Grafana, Prometheus, and Alertmanager
bind only to `127.0.0.1` for operator access through SSH tunneling. Caddy is the only public
service. Port 80 is not published; Caddy can use TLS-ALPN ACME validation on 443.

The `backend` Docker network is `internal: true`. API and worker receive a separate outbound-only
Docker network for external provider calls; no port is published from that network.

## Pinned infrastructure versions

The production Compose file intentionally avoids `latest` tags. V19 pins the validated release
line used by this repository, including Qdrant, Prometheus, Alertmanager, Grafana, Redis,
PostgreSQL, and Caddy. Dependency/image updates should go through CI and security scanning rather
than silently arriving on restart.

## Initial setup

```bash
cp .env.production.example .env.production
mkdir -p secrets
chmod 700 secrets
```

Edit `.env.production` and at minimum set:

```text
TRACTUSMIND_DOMAIN
ACME_EMAIL
LLM_BASE_URL
LLM_MODEL
TRUSTED_HOSTS
```

DNS for `TRACTUSMIND_DOMAIN` must resolve to the production host before the TLS edge starts.

## Secrets

Production Compose mounts secrets under `/run/secrets`. TractusMind supports `*_FILE` for the
application secrets it consumes, so values do not need to appear in Compose environment output.

Generate URL-safe local credentials, for example:

```bash
PG_PASSWORD="$(openssl rand -hex 32)"
REDIS_PASSWORD="$(openssl rand -hex 32)"

printf '%s\n' "$PG_PASSWORD" > secrets/postgres_password
printf '%s\n' "postgresql+asyncpg://tractusmind:${PG_PASSWORD}@postgres:5432/tractusmind" \
  > secrets/database_url

printf '%s\n' "$REDIS_PASSWORD" > secrets/redis_password
printf '%s\n' "redis://:${REDIS_PASSWORD}@redis:6379/0" > secrets/redis_url

openssl rand -base64 48 > secrets/ops_admin_key
openssl rand -base64 48 > secrets/metrics_admin_key
openssl rand -base64 48 > secrets/grafana_admin_password
```

Supply the real provider credentials:

```text
secrets/llm_api_key
secrets/github_token
```

Then restrict permissions:

```bash
chmod 600 secrets/*
```

The `secrets/` directory and `.env.production` are ignored by Git.

## Build and deploy

For a local build on the server:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

For a tagged GHCR release produced by `.github/workflows/release.yml`, set:

```bash
export TRACTUSMIND_IMAGE=ghcr.io/payammirzaei/tractusmind:vX.Y.Z
docker compose --env-file .env.production -f docker-compose.prod.yml pull
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

The one-shot `migrate` service must succeed before API/worker startup. The API independently checks
Alembic head during startup and fails closed if the database revision is stale.

## Health and readiness

```text
GET /health/live   process liveness
GET /health/ready  PostgreSQL + Redis + Qdrant readiness
```

The API container healthcheck uses `/health/live`. Caddy also performs an active liveness check on
the API. `/health/ready` is intentionally stricter and is suitable for deployment verification.

## HTTP security boundary

Production disables interactive OpenAPI docs by default and enables:

- trusted-host validation
- explicit CORS allowlist only when configured
- request-body size limit
- maximum concurrent request guard
- bounded sliding-window request rate limit
- security response headers
- TLS/HSTS at Caddy

Authenticated requests are rate-keyed by a SHA-256-derived opaque token identifier. Anonymous
requests can use the trusted `X-Forwarded-For` address supplied by the private Caddy path.
Credentials are never stored as rate-limit keys or metric labels.

The application rate limiter and provider circuit breakers are **process-local**. They are useful
for one API process and defense in depth, but they are not a distributed quota across multiple API
replicas. A future multi-replica deployment should add a Redis-backed or edge-global limiter.

## Operator observability

The production host exposes these only on loopback:

```text
127.0.0.1:3000  Grafana
127.0.0.1:9090  Prometheus
127.0.0.1:9093  Alertmanager
```

Example SSH tunnel:

```bash
ssh -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 user@server
```

Prometheus authenticates to the production `/metrics` endpoint using the metrics Docker secret as
a Bearer credential. The legacy `X-TractusMind-Metrics-Key` header remains supported for manual
operator requests.

## Graceful shutdown and resources

API, worker, scheduler, PostgreSQL, Redis, and Qdrant have explicit stop grace periods. Application
containers run with a read-only root filesystem, dropped Linux capabilities, `no-new-privileges`,
and writable mounts only where model cache or temporary runtime state is needed.

Compose resource limits are configurable in `.env.production`. The defaults are starting guards,
not benchmark-derived sizing targets; tune them from measured memory/CPU behavior before scaling.

## Backups

Create a PostgreSQL custom-format dump:

```bash
sh scripts/backup-postgres.sh
```

Backups are written under `backups/` with restrictive permissions and are ignored by Git.

A destructive restore requires an explicit confirmation variable:

```bash
RESTORE_CONFIRM=YES sh scripts/restore-postgres.sh backups/tractusmind-postgres-....dump
```

PostgreSQL and Qdrant must be treated as one recovery set. For a short recovery time, keep Qdrant
collection snapshots that correspond to the PostgreSQL state. If Qdrant is lost without a matching
snapshot, rebuild the vector corpus from the allowlisted immutable Git sources before serving
answers; do not assume restored PostgreSQL source state proves Qdrant still contains those chunks.

## Security CI and release images

`.github/workflows/security.yml` scans both the repository and built container image with Trivy and
fails on fixed HIGH/CRITICAL findings. It also scans repository secrets/misconfiguration.

`.github/workflows/release.yml` builds tagged multi-architecture images for GHCR with BuildKit SBOM
and provenance output. Production should deploy a reviewed version tag, never `latest`.

## Rollback

Prefer application-image rollback before database downgrade:

1. stop new rollout
2. select the previous reviewed image tag
3. start the previous application image against the current backward-compatible schema
4. verify `/health/ready` and quality/observability dashboards

Only run an Alembic downgrade when the migration itself is known to be safely reversible and a
PostgreSQL backup has been verified. Schema downgrades and Qdrant storage changes are separate
operations and must not be assumed to roll back together.
