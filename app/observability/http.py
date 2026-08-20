from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import Request, Response
from opentelemetry import trace

from app.observability.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID")
    if supplied is not None:
        normalized = supplied.strip()
        if 1 <= len(normalized) <= 64:
            return normalized
    return str(uuid4())


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
        ).observe(perf_counter() - started)
        structlog.contextvars.clear_contextvars()
