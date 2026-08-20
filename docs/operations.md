# Ingestion operations

TractusMind exposes a small protected operations API for inspecting and triggering source
synchronization. The operations surface is intended for an internal admin UI or operator tooling,
not anonymous public access.

## Authentication

Set a strong secret:

```bash
OPS_ADMIN_KEY=replace-with-a-long-random-secret
```

Send it on every operations request:

```http
X-TractusMind-Admin-Key: replace-with-a-long-random-secret
```

If `OPS_ADMIN_KEY` is unset, `/v1/ops/*` returns `503` instead of silently becoming public. An
invalid or missing header returns `401` when the operations API is configured.

## Read endpoints

```text
GET /v1/ops/summary
GET /v1/ops/sources
GET /v1/ops/sources/{source_id}
GET /v1/ops/runs?source_id=tractusx-sdk&status=failed&limit=50
GET /v1/ops/runs/{run_id}
```

Source status merges the static source registry with PostgreSQL ingestion state and Redis lock
state. It exposes the configured ref, current successful snapshot commit, indexed file count,
last successful run, and the latest run even if that latest run is failed or still running.

Run records expose the delta counters from incremental ingestion:

```text
discovered
added
modified
deleted
unchanged
fetched
chunked
indexed
```

Failed runs include the persisted error message. Because these details may contain internal
runtime information, the read endpoints use the same admin-key protection as mutation endpoints.

## Trigger endpoints

```text
POST /v1/ops/sources/{source_id}/sync
POST /v1/ops/sync
```

The API does not run ingestion inside the HTTP request. It enqueues Dramatiq messages and returns
`202 Accepted` with the broker message ID. Workers then execute the existing Redis-locked,
incremental source-sync path.

Disabled registry sources cannot be triggered individually and return `409 Conflict`.

## Summary semantics

`GET /v1/ops/summary` returns:

- configured and enabled source counts
- indexed source count
- currently locked source count
- sources whose latest run is running or failed
- scheduler interval
- Redis connectivity status
- aggregate ingestion-run status counts from PostgreSQL

This endpoint is intentionally built from the same source state used by ingestion itself rather
than maintaining a second monitoring database.
