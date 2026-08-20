# Architecture

TractusMind is a source-grounded engineering copilot, not a generic chatbot. The system is designed
around provenance, reproducible retrieval, fail-closed grounding, measured quality, and explicit
production boundaries.

## Production topology

```text
Internet
   |
   | TLS 443
   v
 Caddy
   |
   v
 FastAPI API -----------------------> OIDC Provider / JWKS
   |   \----------------------------> LLM provider
   |
   +---------------- private backend ----------------+
   |                |               |                |
PostgreSQL        Redis           Qdrant         Prometheus
   ^                ^               ^                |
   |                |               |            Alertmanager
   |             Dramatiq           |                |
   |                |               |             Grafana
   |             Worker ------------+
   |                |
   |                +---------------------------> GitHub
   |
Scheduler ----------+
```

PostgreSQL, Redis, and Qdrant are not public services. The API and worker have outbound provider
egress without exposing backend ports.

## Identity boundary

Two bearer mechanisms resolve into the same `UserIdentity` and `app_user` ownership model:

```text
API key: tm_...
      or
OIDC access token
      ↓
authentication
      ↓
app_user
      ↓
role: user / operator / admin
      ↓
conversation ownership + RBAC
```

### API-key identities

API keys are generated with strong random material. PostgreSQL stores only SHA-256 digests and a
short non-secret prefix. API-key roles are locally managed.

### OIDC identities

OIDC uses standard discovery and JWKS validation. The configured issuer must match discovery,
access tokens require `iss`, `sub`, and `exp`, the configured audience is verified, algorithms are
allowlisted, and the JWT `kid` must resolve to a signing key. Unknown keys trigger one JWKS refresh
for normal provider key rotation.

A verified external identity is persisted by unique `(issuer, subject)`. This gives it a stable
TractusMind `user_id` across token refreshes and keeps existing conversation foreign keys unchanged.

OIDC role claims map to `user`, `operator`, or `admin`. External roles remain identity-provider
managed; local TractusMind administration may disable the identity but cannot override its role.

`OPS_ADMIN_KEY` is retained only as break-glass admin access.

## RBAC

```text
user
  -> ask / owned conversations / feedback

operator
  -> user capabilities
  -> read source/run/interaction/quality operations

admin
  -> operator capabilities
  -> trigger source synchronization
  -> dismiss/promote quality reviews
  -> create/rotate/disable API-key users
  -> assign API-key roles
```

`admin` inherits `operator`. Authentication is cached only for the lifetime of one HTTP request so
nested FastAPI dependencies do not repeat JWT verification.

## Query path

```text
request
  -> optional API-key/OIDC authentication
  -> conversation ownership check when conversation_id is present
  -> bounded completed history for authenticated owner
  -> current question
  -> deterministic follow-up context rule when needed
  -> deterministic query routing
  -> source/ref/version/snapshot filter
  -> dense retrieval + BM25 sparse retrieval
  -> exact debug lane when applicable
  -> RRF fusion
  -> cross-encoder reranking
  -> calibrated evidence threshold
  -> bounded source context
  -> grounded generation
  -> backend citation validation
  -> atomic claim verification against current evidence
  -> answer or abstention
  -> persisted interaction / trace / citations / verification
  -> optional ownership-checked feedback
```

History is conversational context only. Previous assistant answers are never retrieval/source
evidence and cannot bypass citation or claim verification.

## Source ingestion path

```text
scheduler tick
  -> enabled source IDs from config/sources.toml
  -> Redis / Dramatiq
  -> worker
  -> per-source distributed lock
  -> resolve GitHub ref to immutable commit
  -> discover allowlisted files
  -> compare blob SHA state
  -> fetch/chunk/embed added + modified files only
  -> Qdrant upsert/update/delete
  -> persist successful PostgreSQL source/file/run state
```

Provenance distinguishes:

```text
snapshot_commit_sha = repository snapshot membership
commit_sha          = exact commit containing cited content
```

Unchanged files can move to a newer repository snapshot without weakening exact content/citation
provenance.

## Retrieval contract

Normal queries use dense + BM25 hybrid retrieval, RRF fusion, and cross-encoder reranking. Debug
queries add exact phrase/symbol/parent/path/config retrieval before weighted fusion.

Every hit can carry:

```text
source_id
repository
component
version_ref
snapshot_commit_sha
commit_sha
path / line range
symbol / parent symbol / section
retrieval methods and scores
source URL
```

Explicit `ref:` and `commit:` constraints fail closed when that indexed provenance is unavailable.

## Persistence

PostgreSQL owns durable application state:

- API-key and OIDC identities + role/enable state
- source/file ingestion state and runs
- owned conversations
- answer interactions and trace snapshots
- citations and verification snapshots
- feedback
- quality reviews
- reviewed regression cases

The current Alembic chain is:

```text
0001_core_schema
  -> 0002_user_auth
  -> 0003_oidc_rbac
```

Runtime code does not create or alter PostgreSQL tables.

## Quality loop

```text
failed answer / down-vote
          ↓
 pending quality review
          ↓
     human root cause
       /       \
  dismiss    promote
                ↓
         regression case
                ↓
         reviewed benchmark
                ↓
         production gate
```

Raw feedback is never automatically promoted to gold data.

## Full-corpus validation

A production benchmark is considered valid only after the corpus contract verifies every enabled
source across PostgreSQL and Qdrant, with optional upstream GitHub freshness validation.

The V20 workflow records source snapshots, upstream commits, model identities, input hashes,
retrieval/answer metrics, and the measured calibration threshold. Thresholds are proposed as
artifacts and require human review before they are pinned.

## Observability

Prometheus observes API/RAG/provider/model/worker/ingestion/quality paths. Grafana dashboards are
provisioned from the repository and Alertmanager evaluates repository-owned alerts. OpenTelemetry
traces are optional and exported only when an OTLP endpoint is configured.

Request IDs and trace IDs belong in logs/traces, not metric labels. Questions, source text, secrets,
raw paths, commit hashes, and error bodies are not used as unbounded metric labels.

## Production hardening

The production Compose topology adds:

- Caddy TLS edge and security headers
- TrustedHost/CORS policy
- body-size, concurrency, and process-local rate guards
- Docker secret-file configuration
- read-only application roots and dropped capabilities
- `no-new-privileges`
- resource limits and graceful shutdown
- pinned infrastructure image tags
- PostgreSQL backup/guarded restore
- Trivy repository/image scanning
- tagged GHCR images with SBOM/provenance

## Inspectability principle

A production answer remains explainable as:

```text
identity + role
  -> owned history eligibility
  -> question
  -> route
  -> source/ref/snapshot filter
  -> candidate lanes and scores
  -> fusion + reranking
  -> evidence threshold
  -> final evidence
  -> provider request/retry path
  -> answer
  -> citations
  -> verification verdicts
  -> persisted interaction + trace
  -> optional feedback/review/regression
```

No hidden RAG magic: each stage is intended to be inspectable, testable, and replaceable without
changing the provenance contract.
