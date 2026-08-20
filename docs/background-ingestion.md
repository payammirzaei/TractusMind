# Background ingestion

TractusMind can synchronize allowlisted Tractus-X sources without a human running the ingestion
CLI. The background path reuses the exact same incremental synchronization service used by
`tractusmind-ingest sync`, so scheduled ingestion and manual ingestion do not diverge.

## Runtime components

```text
scheduler
   |
   | enqueue enabled source IDs
   v
Redis / Dramatiq
   |
   v
worker
   |
   +--> per-source Redis distributed lock
   |
   v
IncrementalSourceSync
   |
   +--> GitHub manifest discovery
   +--> PostgreSQL source/file state
   +--> added/modified-only fetch + chunk + embedding
   +--> Qdrant snapshot update/delete/upsert
   +--> ingestion_run audit record
```

The scheduler runs as a separate process/container. By default it enqueues all enabled sources
immediately on startup and then every six hours. The interval is configurable:

```bash
SOURCE_SYNC_INTERVAL_SECONDS=21600
```

The worker uses one process and one thread in the default Compose topology because indexing can
load dense, sparse, and reranker models into memory. Horizontal worker scaling is still safe:
each source sync is protected by a Redis distributed lock.

## Distributed source lock

Each job tries to acquire:

```text
tractusmind:source-sync:<source_id>
```

Lock acquisition is non-blocking. If another worker already owns the same source lock, the job
returns `status=locked` instead of waiting and creating a retry storm. The lock has an expiry so
a crashed worker cannot hold a source forever:

```bash
SOURCE_SYNC_LOCK_SECONDS=43200
```

The configured TTL should exceed the longest expected full baseline sync. Resource cleanup and
lock release run in `finally`, including failures that happen while creating Postgres or Qdrant
clients. If a lock expires before release, the worker logs the condition instead of masking the
original sync result.

## Worker retries

The Dramatiq source actor has three retries. Runtime failures therefore retry through the same
idempotent incremental ingestion path documented in `incremental-ingestion.md`. PostgreSQL only
advances the successful source snapshot after Qdrant operations succeed, so a retry recomputes
the same delta when necessary.

## Manual queue controls

Queue one source without doing the work in the caller process:

```bash
tractusmind-ingest enqueue tractusx-sdk
```

Queue every enabled source:

```bash
tractusmind-ingest enqueue-all
```

Run one scheduler cycle and exit:

```bash
tractusmind-scheduler --once
```

Run the long-lived scheduler:

```bash
tractusmind-scheduler
```

For debugging, the direct synchronous-style command remains available:

```bash
tractusmind-ingest sync tractusx-sdk
```

## Deployment topology

The default Docker Compose stack has separate `api`, `worker`, and `scheduler` services. The
source registry is copied into the runtime image and mounted read-only into worker/scheduler in
local Compose, so scheduled jobs and CLI runs resolve the same `config/sources.toml` allowlist.

No unauthenticated HTTP endpoint is exposed for enqueueing ingestion work. Until authentication
and authorization exist, expensive ingestion mutations remain an operator/CLI capability rather
than a public API action.
