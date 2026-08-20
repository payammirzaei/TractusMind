# Versioned database migrations

TractusMind uses Alembic as the only supported PostgreSQL schema-mutation path.

Application requests, background workers, and stores do **not** call `create_all()` or execute
compatibility `ALTER TABLE` statements. They verify that PostgreSQL is at the application migration
head and fail fast when it is not.

## Current revision chain

```text
0001_core_schema
  -> 0002_user_auth   (head)
```

`0001_core_schema` represents the managed schema through V14:

- source state and source-file state
- ingestion runs
- conversations and answer interactions
- feedback
- quality reviews
- reviewed regression cases

`0002_user_auth` adds:

- `app_user`
- API-key identity indexes
- `conversation.owner_user_id`
- the owner index and foreign-key constraint

## Normal deployment

The recommended deployment command is:

```bash
tractusmind-db bootstrap
```

`bootstrap` is safe for three known states:

1. **Fresh database** — runs all migrations to `head`.
2. **Already versioned database** — runs normal `upgrade head`.
3. **Complete pre-Alembic TractusMind database** — stamps `0001_core_schema`, then runs the
   idempotent V15 ownership migration to `head`.

A partial legacy schema is rejected. TractusMind does not guess which missing tables are safe to
reconstruct around existing production data.

Docker Compose runs the one-shot `migrate` service before API and worker startup.

## Operator commands

```bash
# Safely adopt or upgrade the database used by deployments
tractusmind-db bootstrap

# Normal versioned upgrade
tractusmind-db upgrade

# Upgrade to a specific revision
tractusmind-db upgrade 0002_user_auth

# Verify that the database matches the application head
tractusmind-db check

# Fail if ORM metadata differs from the migrated database
tractusmind-db drift

# Inspect revision state/history
tractusmind-db current
tractusmind-db history

# Explicit rollback; take a backup first
tractusmind-db downgrade 0001_core_schema
```

`drift` wraps Alembic's schema comparison. It catches the case where an ORM model changes but the
corresponding numbered migration was forgotten.

`stamp` is exposed for recovery/operator use, but normal deployment should prefer `bootstrap`:

```bash
tractusmind-db stamp 0001_core_schema
```

Stamping records migration state without executing DDL. Do not stamp an unverified partial schema.

## Runtime policy

The API checks the database revision during FastAPI startup. Background ingestion checks the same
revision before source-state work begins. Auth, conversation, and quality stores also keep a
one-time per-process revision guard before their first database operation.

If the revision is missing or stale, runtime fails with an instruction to run:

```text
tractusmind-db bootstrap
```

This avoids a dangerous state where one application replica silently mutates shared schema while
another replica is still serving traffic.

## Legacy adoption safety

The bootstrap baseline requires all V14 core tables to exist before it will stamp an unversioned
legacy database. V15's `0002_user_auth` migration is intentionally idempotent so databases that
already created `app_user` or `owner_user_id` before Alembic adoption can still be normalized. It
adds missing indexes/constraints instead of recreating existing objects.

The ownership foreign key uses `ON DELETE RESTRICT`; deleting an identity cannot silently convert
owned conversation history into anonymous history.

## CI contract

CI starts a real PostgreSQL 17 service and validates:

```text
fresh bootstrap
  -> revision check
  -> ORM/Alembic drift check
  -> pytest
  -> remove alembic_version only
  -> legacy bootstrap adoption
  -> revision check
  -> downgrade to 0001_core_schema
  -> upgrade to head
  -> revision check
  -> ORM/Alembic drift check
```

The legacy smoke test intentionally keeps all managed tables while removing only Alembic's version
marker. This reproduces the transition from the pre-V16 TractusMind database.

## Migration rules

- Never edit a migration revision after it has been used by a shared environment.
- Add a new numbered revision for every schema change.
- Keep data migrations explicit and bounded; do not hide them in application startup.
- Back up production PostgreSQL before destructive downgrades.
- Prefer additive, backward-compatible migrations when rolling multiple replicas.
- Do not make Qdrant schema/index migration depend implicitly on PostgreSQL Alembic state; track
  those storage changes separately.
