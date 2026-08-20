from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import Request, Response

from app.observability.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS


async def observe_http_request(request: Request, call_next) -> Response:
    if request.url.path == "/metrics":
        return await call_next(request)

    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
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
