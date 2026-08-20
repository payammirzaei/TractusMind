# Versioned database migrations

TractusMind uses Alembic as the only supported PostgreSQL schema-mutation path. Runtime services do
not call `create_all()` or silently alter tables; they verify the migration head and fail fast.

## Current revision chain

```text
0001_core_schema
  -> 0002_user_auth
  -> 0003_oidc_rbac   (head)
```

`0001_core_schema` represents the managed schema through V14: source/file state, ingestion runs,
conversations/interactions, feedback, quality reviews, and regression cases.

`0002_user_auth` adds API-key users and `conversation.owner_user_id`.

`0003_oidc_rbac` adds:

- `app_user.auth_type`
- `app_user.role`
- nullable API-key fields for external identities
- `oidc_issuer` and `oidc_subject`
- unique `(oidc_issuer, oidc_subject)` identity index

Existing API-key users are migrated with `auth_type=api_key` and `role=user`.

## Normal deployment

```bash
tractusmind-db bootstrap
```

`bootstrap` handles fresh databases, already-versioned databases, and complete pre-Alembic legacy
TractusMind schemas. Partial legacy schemas are rejected rather than guessed around existing data.

Docker Compose runs the one-shot migration service before API and worker startup.

## Operator commands

```bash
tractusmind-db bootstrap
tractusmind-db upgrade
tractusmind-db upgrade 0003_oidc_rbac
tractusmind-db check
tractusmind-db drift
tractusmind-db current
tractusmind-db history
```

Take a backup before explicit rollback:

```bash
tractusmind-db downgrade 0002_user_auth
```

Downgrading `0003_oidc_rbac` is deliberately blocked when OIDC identities exist. Converting those
rows back into mandatory API-key users would require inventing credentials or deleting identity
records, so the migration fails instead of causing silent data loss.

`drift` wraps Alembic schema comparison and catches ORM changes that were made without a numbered
migration.

## Runtime policy

The API verifies the database revision at startup. Background ingestion and state stores verify the
same application head before database work. A stale or missing revision fails with an instruction
to run `tractusmind-db bootstrap`.

This prevents one replica from mutating shared schema while another serves traffic on a different
contract.

## Legacy adoption safety

The bootstrap baseline requires all managed core tables before it stamps an unversioned legacy
database. `0002_user_auth` remains idempotent for the historical pre-Alembic user/owner transition;
normal subsequent revisions use standard ordered migration semantics.

The conversation ownership foreign key uses `ON DELETE RESTRICT`, so deleting an identity cannot
silently turn owned history into anonymous history.

## CI contract

CI uses PostgreSQL and validates:

```text
fresh bootstrap
  -> revision check
  -> ORM/Alembic drift check
  -> pytest
  -> legacy-version-marker adoption smoke test
  -> downgrade through auth revisions when no external identities exist
  -> upgrade to head
  -> revision check
  -> ORM/Alembic drift check
```

## Migration rules

- Never edit a migration revision after it has been used by a shared environment.
- Add a numbered revision for every schema change.
- Keep data migrations explicit and bounded.
- Back up production PostgreSQL before destructive downgrades.
- Prefer additive/backward-compatible migrations during rolling deployment.
- Do not hide schema mutation in API startup or request handlers.
- Track Qdrant index/schema evolution separately from PostgreSQL Alembic state.
