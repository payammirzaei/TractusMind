from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import Request, Response
from opentelemetry import trace

from app.core.config import get_settings
from app.observability.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS

logger = structlog.get_logger()

_ACTIVITY_EXCLUDED_PATHS = {"/metrics", "/v1/activity/events"}


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID")
    if supplied is not None:
        normalized = supplied.strip()
        if 1 <= len(normalized) <= 64:
            return normalized
    return str(uuid4())


def _client_ip(request: Request) -> str | None:
    if get_settings().trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            address = forwarded.split(",", 1)[0].strip()
            if address:
                return address[:64]
    if request.client is None:
        return None
    return request.client.host[:64]


def _should_persist(path: str) -> bool:
    if path in _ACTIVITY_EXCLUDED_PATHS:
        return False
    if path.startswith("/health/"):
        return False
    if path.startswith("/v1/ops/"):
        return False
    return True


async def observe_http_request(request: Request, call_next) -> Response:
    if request.url.path == "/metrics":
        return await call_next(request)

    request_id = _request_id(request)
    request.state.request_id = request_id
    log_context = {"request_id": request_id}
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        log_context["trace_id"] = f"{span_context.trace_id:032x}"
    structlog.contextvars.bind_contextvars(**log_context)
    started = perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_seconds = perf_counter() - started
        route = request.scope.get("route")
        route_template = getattr(route, "path", "unmatched")
        method = request.method
        HTTP_REQUESTS.labels(
            method=method,
            route=route_template,
            status=str(status_code),
        ).inc()
        HTTP_REQUEST_DURATION.labels(
            method=method,
            route=route_template,
        ).observe(duration_seconds)

        store = getattr(request.app.state, "activity_store", None)
        if store is not None and _should_persist(request.url.path):
            identity = getattr(request.state, "auth_identity", None)
            user_id = getattr(identity, "user_id", None)
            try:
                await store.record_event(
                    event_type="http_request",
                    path=request.url.path,
                    user_id=user_id,
                    request_id=request_id,
                    ip_address=_client_ip(request),
                    method=method,
                    status_code=status_code,
                    duration_ms=duration_seconds * 1000.0,
                    referrer=request.headers.get("referer"),
                    user_agent=request.headers.get("user-agent"),
                )
            except Exception as exc:
                logger.warning(
                    "http_activity_store_failed",
                    error_type=type(exc).__name__,
                    path=request.url.path,
                )

        structlog.contextvars.clear_contextvars()
