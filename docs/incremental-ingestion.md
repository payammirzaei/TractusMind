# Incremental ingestion

TractusMind keeps source synchronization state in PostgreSQL and uses Git blob SHAs as cheap,
content-addressed file fingerprints. A normal sync discovers the current repository tree first,
compares it with the last successful snapshot, and fetches only added or modified files.

## State model

PostgreSQL stores three kinds of state:

- `source_state`: current successful source ref and snapshot commit.
- `source_file_state`: path, blob SHA, content commit, and last-seen snapshot for each file.
- `ingestion_run`: auditable run history and added/modified/deleted/unchanged counters.

The state is advanced only after the Qdrant operations for a run succeed. Failed runs are marked
as failed and retain the previous successful snapshot, so retrying computes the same delta again.
Qdrant writes are intentionally idempotent: changed chunks use deterministic point IDs, payload
updates may be repeated, and path cleanup may be repeated safely.

## Snapshot versus content commit

Incremental indexing distinguishes two provenance values:

- `snapshot_commit_sha`: repository snapshot the indexed point currently belongs to.
- `commit_sha`: exact commit from which that file content was fetched and cited.

If a file is unchanged between two repository commits, TractusMind does not download, chunk, or
embed it again. Only its `version_ref` and `snapshot_commit_sha` payload fields are updated. Its
`commit_sha` and commit-pinned citation URL remain attached to the earlier commit where the exact
content was fetched.

This lets an explicit `commit:<sha>` query select the complete requested repository snapshot while
citations still point to an immutable commit containing the exact cited bytes.

## Sync flow

```text
GitHub manifest at immutable commit
        |
        v
load last successful PostgreSQL state
        |
        v
compare path + Git blob SHA
        |
        +--> added ---------+
        +--> modified ------+--> fetch -> chunk -> dense/BM25 -> Qdrant upsert
        +--> unchanged --------> metadata-only snapshot update
        +--> deleted ----------> Qdrant path delete
        |
        v
commit source/file state + ingestion run in PostgreSQL
```

Run one source incrementally:

```bash
tractusmind-ingest sync tractusx-sdk
```

The first managed sync establishes the PostgreSQL baseline. Later runs process only the delta.
The command prints the run ID, snapshot commit, and counts for discovered, added, modified,
deleted, unchanged, fetched, chunked, and indexed items.

## Recovery model

PostgreSQL and Qdrant do not share a distributed transaction. TractusMind therefore favors
idempotent recovery over pretending they are atomic. If a run fails after a partial Qdrant write,
the PostgreSQL successful snapshot is not advanced. The next retry recomputes the same changes and
re-applies deterministic upserts, metadata updates, and deletes.

A future source-state API can expose incomplete/failed runs and reconciliation status for
operations dashboards.
