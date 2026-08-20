from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.ops_auth import require_ops_admin
from app.core.config import get_settings
from app.ingestion.registry import get_source, load_source_registry
from app.state.store import IngestionRunRecord, SourceStateStore
from app.workers.tasks import sync_source_task

router = APIRouter(
    prefix="/v1/ops",
    tags=["operations"],
    dependencies=[Depends(require_ops_admin)],
)


class SourceOpsStatus(BaseModel):
    source_id: str
    repository: str
    component: str
    priority: str
    enabled: bool
    configured_ref: str
    version_ref: str | None = None
    snapshot_commit_sha: str | None = None
    file_count: int = Field(default=0, ge=0)
    last_successful_run_id: str | None = None
    updated_at: datetime | None = None
    locked: bool = False


class RunOpsStatus(BaseModel):
    run_id: str
    source_id: str
    repository: str
    requested_ref: str
    snapshot_commit_sha: str
    status: str
    discovered_count: int
    added_count: int
    modified_count: int
    deleted_count: int
    unchanged_count: int
    fetched_count: int
    chunk_count: int
    indexed_count: int
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class OpsSummary(BaseModel):
    configured_sources: int
    enabled_sources: int
    indexed_sources: int
    locked_sources: int
    scheduler_interval_seconds: int
    redis_ok: bool
    run_status_counts: dict[str, int]


class EnqueueResult(BaseModel):
    source_id: str
    status: Literal["queued"] = "queued"
    message_id: str


class EnqueueManyResult(BaseModel):
    status: Literal["queued"] = "queued"
    count: int
    jobs: list[EnqueueResult]


async def _store(request: Request) -> SourceStateStore:
    store = SourceStateStore(request.app.state.postgres)
    await store.ensure_schema()
    return store


async def _is_locked(request: Request, source_id: str) -> bool:
    return bool(await request.app.state.redis.exists(f"tractusmind:source-sync:{source_id}"))


def _run_response(run: IngestionRunRecord) -> RunOpsStatus:
    return RunOpsStatus(**run.__dict__)


async def _source_responses(request: Request) -> list[SourceOpsStatus]:
    store = await _store(request)
    persisted = {item.source_id: item for item in await store.list_source_statuses()}
    responses: list[SourceOpsStatus] = []

    for source in load_source_registry():
        state = persisted.get(source.id)
        responses.append(
            SourceOpsStatus(
                source_id=source.id,
                repository=source.full_name,
                component=source.component,
                priority=source.priority.value,
                enabled=source.enabled,
                configured_ref=source.ref,
                version_ref=state.version_ref if state else None,
                snapshot_commit_sha=state.snapshot_commit_sha if state else None,
                file_count=state.file_count if state else 0,
                last_successful_run_id=(state.last_successful_run_id if state else None),
                updated_at=state.updated_at if state else None,
                locked=await _is_locked(request, source.id),
            )
        )
    return responses


def _enqueue(source_id: str) -> EnqueueResult:
    message = sync_source_task.send(source_id)
    return EnqueueResult(source_id=source_id, message_id=message.message_id)


@router.get("/summary", response_model=OpsSummary)
async def summary(request: Request) -> OpsSummary:
    sources = await _source_responses(request)
    store = await _store(request)
    try:
        redis_ok = bool(await request.app.state.redis.ping())
    except Exception:
        redis_ok = False

    return OpsSummary(
        configured_sources=len(sources),
        enabled_sources=sum(item.enabled for item in sources),
        indexed_sources=sum(item.snapshot_commit_sha is not None for item in sources),
        locked_sources=sum(item.locked for item in sources),
        scheduler_interval_seconds=get_settings().source_sync_interval_seconds,
        redis_ok=redis_ok,
        run_status_counts=await store.run_status_counts(),
    )


@router.get("/sources", response_model=list[SourceOpsStatus])
async def sources(request: Request) -> list[SourceOpsStatus]:
    return await _source_responses(request)


@router.get("/sources/{source_id}", response_model=SourceOpsStatus)
async def source_status(source_id: str, request: Request) -> SourceOpsStatus:
    for item in await _source_responses(request):
        if item.source_id == source_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown source id")


@router.get("/runs", response_model=list[RunOpsStatus])
async def runs(
    request: Request,
    source_id: str | None = None,
    run_status: Literal["running", "succeeded", "failed"] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RunOpsStatus]:
    store = await _store(request)
    records = await store.list_runs(
        source_id=source_id,
        status=run_status,
        limit=limit,
    )
    return [_run_response(item) for item in records]


@router.get("/runs/{run_id}", response_model=RunOpsStatus)
async def run(run_id: str, request: Request) -> RunOpsStatus:
    store = await _store(request)
    record = await store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run id")
    return _run_response(record)


@router.post(
    "/sources/{source_id}/sync",
    response_model=EnqueueResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_source(source_id: str) -> EnqueueResult:
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
    return _enqueue(source_id)


@router.post(
    "/sync",
    response_model=EnqueueManyResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_all() -> EnqueueManyResult:
    jobs = [_enqueue(source.id) for source in load_source_registry() if source.enabled]
    return EnqueueManyResult(count=len(jobs), jobs=jobs)
