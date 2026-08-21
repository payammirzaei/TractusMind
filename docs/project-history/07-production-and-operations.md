# 07 — Production, Observability and Release Engineering

## Production topology

The production deployment was separated from local development and hardened around a small public edge.

Conceptually:

```text
Internet
  -> Caddy / TLS
  -> Mission Control + FastAPI
  -> private backend network
       -> PostgreSQL
       -> Redis
       -> Qdrant
       -> worker
       -> scheduler
       -> Prometheus
       -> Grafana
       -> Alertmanager
```

Only the edge is intended to be publicly reachable. Data services remain internal.

## Docker hardening

Application containers were hardened with combinations of:

- read-only root filesystems,
- explicit tmpfs locations,
- dropped Linux capabilities,
- `no-new-privileges`,
- init handling,
- restart policy,
- resource limits,
- stop grace periods.

The goal is to make the Compose topology closer to a controlled production runtime rather than a permissive local development stack.

## Docker secrets

Production-sensitive values are loaded through mounted secret files where supported.

Examples include:

- database URL/password,
- Redis URL/password,
- LLM API key,
- GitHub token,
- operations admin key,
- metrics key,
- Grafana admin password.

The application supports `*_FILE` style settings so secret values do not need to be copied into normal Compose environment output.

## Database migrations

Alembic migrations became part of startup correctness.

The production topology uses a one-shot migration/bootstrap service before API/worker startup. The API also verifies schema head at startup and fails closed if the database is stale.

This prevents “application image updated, schema forgotten” deployments.

## Health model

The backend exposes separate concepts:

- `/health/live` — process liveness,
- `/health/ready` — dependency readiness.

Readiness includes PostgreSQL, Redis and Qdrant.

Mission Control also exposes its own runtime health and reads backend readiness through the BFF.

## Caddy edge

Caddy provides the production HTTPS edge and HSTS/security policy. The architecture was designed so domain/TLS concerns remain outside the application containers.

A production-runtime CI gate is being used to exercise this hardened topology with internal/local TLS before final public deployment. The real public deployment still requires actual DNS/domain/provider inputs.

## Observability

The project added Prometheus/OpenTelemetry-oriented instrumentation and operator surfaces for:

- API behavior,
- model operation duration/load,
- provider health/failure,
- worker/scheduler behavior,
- application health,
- ingestion/quality operations.

Production Compose includes Prometheus, Grafana and Alertmanager. Operator web ports bind to loopback rather than the public network and can be reached through SSH tunneling.

## Alerting

Grafana/Prometheus configuration provides the base for alerting on runtime failures and unhealthy system conditions instead of relying exclusively on application logs.

## Backup and restore

A PostgreSQL backup script writes custom-format dumps into an ignored backup directory with restrictive permissions.

Restore is intentionally destructive and requires an explicit confirmation variable.

An important recovery decision was documented: PostgreSQL and Qdrant form one logical recovery set. Restoring SQL metadata without the corresponding vector state does not prove the corpus is valid. If Qdrant state is unavailable, the vector corpus should be rebuilt from the allowlisted immutable Git sources before serving trusted answers.

## Release engineering

Release workflow work expanded from backend-only publishing to include both:

- backend image,
- Mission Control image.

The target release process builds versioned multi-architecture container images and includes BuildKit SBOM/provenance output.

Production should deploy reviewed version tags, never `latest`.

## Rollback model

The preferred rollback sequence is application-first:

1. stop the rollout,
2. select the previous reviewed application image,
3. start it against the current backward-compatible schema,
4. verify readiness and quality/observability,
5. only consider a database downgrade when the migration is known to be safely reversible and a verified backup exists.

## Production smoke

A dedicated production smoke client was added to verify an actual HTTPS deployment.

It checks:

- TLS edge,
- security headers,
- Mission Control health,
- backend readiness through BFF,
- authenticated session creation,
- core browser routes,
- operator/admin endpoints according to role,
- logout/session rejection.

This smoke requires a real deployment URL and a TractusMind API key, so it remains one of the final external-input gates before `v1.0.0`.

See also:

- [`../production-deployment.md`](../production-deployment.md)
- [`../database-migrations.md`](../database-migrations.md)
- [`../observability.md`](../observability.md)
- [`../grafana-alerting.md`](../grafana-alerting.md)
- [`../operations.md`](../operations.md)
