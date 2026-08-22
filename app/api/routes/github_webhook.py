import json

import structlog
from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import get_settings
from app.ingestion.registry import get_enabled_sources
from app.ingestion.webhook import matching_push_sources, verify_github_signature
from app.observability.metrics import QUEUE_ENQUEUED
from app.workers.tasks import sync_source_task

logger = structlog.get_logger()
router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def _delivery_key(delivery_id: str) -> str:
    return f"tractusmind:webhook:github:delivery:{delivery_id}"


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(request: Request) -> dict[str, object]:
    settings = get_settings()
    secret = settings.github_webhook_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub webhook ingestion is not configured",
        )

    body = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not verify_github_signature(body=body, signature=signature, secret=secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub webhook signature",
        )

    event = request.headers.get("x-github-event", "").strip().casefold()
    delivery_id = request.headers.get("x-github-delivery", "").strip()
    if not delivery_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-GitHub-Delivery header",
        )

    delivery_key = _delivery_key(delivery_id)
    # GitHub can retry deliveries. Claim the delivery id before doing any work so
    # concurrent replays never create duplicate queue traffic. Failures delete the
    # claim again so GitHub's retry remains useful instead of silently losing work.
    claimed = await request.app.state.redis.set(
        delivery_key,
        "1",
        ex=settings.github_webhook_delivery_ttl_seconds,
        nx=True,
    )
    if not claimed:
        return {
            "accepted": True,
            "duplicate": True,
            "event": event or "unknown",
            "queued_sources": [],
        }

    if event == "ping":
        return {
            "accepted": True,
            "duplicate": False,
            "event": "ping",
            "queued_sources": [],
        }
    if event != "push":
        return {
            "accepted": True,
            "duplicate": False,
            "event": event or "unknown",
            "ignored": True,
            "queued_sources": [],
        }

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        await request.app.state.redis.delete(delivery_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub webhook JSON",
        ) from exc
    if not isinstance(payload, dict):
        await request.app.state.redis.delete(delivery_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub webhook JSON must be an object",
        )

    if payload.get("deleted") is True:
        return {
            "accepted": True,
            "duplicate": False,
            "event": "push",
            "ignored": True,
            "reason": "deleted_ref",
            "queued_sources": [],
        }

    repository = payload.get("repository") or {}
    if not isinstance(repository, dict):
        await request.app.state.redis.delete(delivery_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub push payload has an invalid repository object",
        )
    repository_full_name = str(repository.get("full_name") or "")
    push_ref = str(payload.get("ref") or "")
    if not repository_full_name or not push_ref:
        await request.app.state.redis.delete(delivery_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub push payload is missing repository.full_name or ref",
        )

    sources = matching_push_sources(
        repository_full_name=repository_full_name,
        push_ref=push_ref,
        sources=get_enabled_sources(),
    )
    queued_sources: list[str] = []
    try:
        for source in sources:
            sync_source_task.send(source.id)
            QUEUE_ENQUEUED.labels(origin="github_webhook").inc()
            queued_sources.append(source.id)
    except Exception:
        await request.app.state.redis.delete(delivery_key)
        logger.exception(
            "github_webhook_enqueue_failed",
            delivery_id=delivery_id,
            repository=repository_full_name,
            ref=push_ref,
            queued_sources=queued_sources,
        )
        raise

    logger.info(
        "github_webhook_processed",
        delivery_id=delivery_id,
        repository=repository_full_name,
        ref=push_ref,
        queued_sources=queued_sources,
    )
    return {
        "accepted": True,
        "duplicate": False,
        "event": "push",
        "repository": repository_full_name,
        "ref": push_ref,
        "queued_sources": queued_sources,
    }
