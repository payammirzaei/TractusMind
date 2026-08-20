# Operations API

TractusMind exposes protected operations endpoints for source state, ingestion runs, answer traces,
quality review, and administrative actions. The surface is intended for Mission Control/operator
tooling, not anonymous access.

## Authentication

Normal operations access uses the same bearer identity layer as the rest of TractusMind:

```http
Authorization: Bearer tm_...
```

or a verified enterprise OIDC access token:

```http
Authorization: Bearer <OIDC JWT>
```

Roles are hierarchical:

```text
user < operator < admin
```

A valid `user` without sufficient operations privileges receives `403`. Missing/invalid bearer
authentication receives `401`.

## Break-glass admin

`OPS_ADMIN_KEY` remains supported for emergency/bootstrap access:

```http
X-TractusMind-Admin-Key: <secret>
```

A matching key is treated as `admin`. Do not distribute this shared credential to normal human
operators once API-key roles or OIDC are configured.

## Operator read endpoints

`operator` and `admin` can inspect:

```text
GET /v1/ops/summary
GET /v1/ops/sources
GET /v1/ops/sources/{source_id}
GET /v1/ops/runs
GET /v1/ops/runs/{run_id}
GET /v1/ops/interactions
GET /v1/ops/interactions/{interaction_id}
GET /v1/ops/feedback/summary
GET /v1/ops/quality/summary
GET /v1/ops/quality/reviews
GET /v1/ops/quality/reviews/{review_id}
GET /v1/ops/quality/regressions
GET /v1/ops/quality/regressions/export
```

Read-only operator access is intentionally sufficient for dashboards, investigation, and quality
triage without granting mutation permissions.

## Admin mutations

Only `admin` can mutate operational state:

```text
POST  /v1/ops/sources/{source_id}/sync
POST  /v1/ops/sync
POST  /v1/ops/quality/reviews/{review_id}/decision
GET   /v1/ops/users
POST  /v1/ops/users
POST  /v1/ops/users/{user_id}/rotate
PATCH /v1/ops/users/{user_id}
```

User lifecycle endpoints are admin-only even when they are reads, because they expose credential
metadata and identity-management state.

OIDC user roles are controlled by identity-provider claims. TractusMind administrators may locally
disable or re-enable an OIDC identity, but attempts to override its role return `409`. API-key
identity roles remain locally manageable.

## Source operations

Source status merges the static source registry with PostgreSQL ingestion state and Redis lock
state. It exposes configured ref, successful snapshot commit, indexed file count, last successful
run, and the latest run even if it failed or is still running.

Trigger endpoints enqueue Dramatiq messages and return `202 Accepted`; they do not execute
synchronization inline. Workers continue through the Redis-locked incremental ingestion path.

Disabled registry sources cannot be manually triggered and return `409 Conflict`.

## Current identity

Authenticated clients can resolve the identity/role used for UI authorization with:

```text
GET /v1/me
```

The response contains only:

```text
user_id
display_name
role
auth_type
```

It does not expose API-key hashes, OIDC subjects/issuers, or bearer token contents.
