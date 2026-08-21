from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.ops_auth import require_ops_admin
from app.ingestion.incremental import build_incremental_plan
from app.ingestion.models import SourceFile, SourceManifest
from app.ingestion.registry import get_source
from app.state.store import SourceStateStore

router = APIRouter(
    prefix="/v1/ops",
    tags=["operations"],
    dependencies=[Depends(require_ops_admin)],
)


class AdoptedFile(BaseModel):
    path: str = Field(min_length=1)
    blob_sha: str = Field(min_length=7, max_length=64)
    size_bytes: int = Field(default=0, ge=0)
    content_type: str = Field(min_length=1, max_length=64)


class AdoptSnapshotRequest(BaseModel):
    version_ref: str = Field(min_length=1, max_length=255)
    snapshot_commit_sha: str = Field(min_length=7, max_length=64)
    files: list[AdoptedFile]
    chunk_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)


class AdoptSnapshotResponse(BaseModel):
    source_id: str
    run_id: str
    snapshot_commit_sha: str
    file_count: int
    chunk_count: int
    indexed_count: int
    status: str = "succeeded"


@router.post(
    "/sources/{source_id}/adopt-snapshot",
    response_model=AdoptSnapshotResponse,
)
async def adopt_snapshot(
    source_id: str,
    payload: AdoptSnapshotRequest,
    request: Request,
) -> AdoptSnapshotResponse:
    """Adopt an externally indexed, fully verified source snapshot.

    This endpoint does not fetch source content or create embeddings. It is intended
    for trusted bulk-indexing workers that already wrote the exact TractusMind vector
    payloads to Qdrant and need to reconcile Postgres source state afterwards.
    """

    try:
        source = get_source(source_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown source id",
        ) from exc

    if not source.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source is disabled in the registry",
        )
    if payload.version_ref != source.ref:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Snapshot ref {payload.version_ref!r} does not match configured ref {source.ref!r}",
        )
    if payload.indexed_count != payload.chunk_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only fully indexed snapshots can be adopted",
        )

    paths = [item.path for item in payload.files]
    if len(paths) != len(set(paths)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Snapshot contains duplicate file paths",
        )

    locked = bool(await request.app.state.redis.exists(f"tractusmind:source-sync:{source_id}"))
    if locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A Railway source sync is active; retry adoption after it finishes",
        )

    manifest = SourceManifest(
        source_id=source.id,
        repository=source.full_name,
        component=source.component,
        requested_ref=payload.version_ref,
        commit_sha=payload.snapshot_commit_sha,
        archived=False,
        files=[
            SourceFile(
                path=item.path,
                sha=item.blob_sha,
                size=item.size_bytes,
                content_type=item.content_type,
            )
            for item in payload.files
        ],
    )

    store = SourceStateStore(request.app.state.postgres)
    await store.ensure_schema()
    previous_files = await store.load_file_states(source_id)
    plan = build_incremental_plan(manifest, previous_files)
    run_id = await store.start_run(manifest)
    try:
        await store.complete_run(
            run_id=run_id,
            manifest=manifest,
            added_paths={item.path for item in plan.added},
            modified_paths={item.path for item in plan.modified},
            deleted_paths=set(plan.deleted_paths),
            unchanged_paths={item.path for item in plan.unchanged},
            fetched_count=len(payload.files),
            chunk_count=payload.chunk_count,
            indexed_count=payload.indexed_count,
            previous_files=previous_files,
        )
    except Exception as exc:
        await store.fail_run(run_id, exc)
        raise

    return AdoptSnapshotResponse(
        source_id=source_id,
        run_id=run_id,
        snapshot_commit_sha=payload.snapshot_commit_sha,
        file_count=len(payload.files),
        chunk_count=payload.chunk_count,
        indexed_count=payload.indexed_count,
    )
