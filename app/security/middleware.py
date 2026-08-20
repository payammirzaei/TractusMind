import asyncio
import hashlib
from collections import deque
from time import monotonic

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLarge(RuntimeError):
    pass


class SlidingWindowRateLimiter:
    def __init__(self, *, requests: int, window_seconds: float, max_keys: int = 10_000) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> tuple[bool, int]:
        now = monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self.max_keys:
                    self._purge(cutoff)
                if len(self._events) >= self.max_keys:
                    key = "overflow"
                events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.requests:
                retry_after = max(1, int(self.window_seconds - (now - events[0])))
                return False, retry_after
            events.append(now)
            return True, 0

    def _purge(self, cutoff: float) -> None:
        stale: list[str] = []
        for key, events in self._events.items():
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                stale.append(key)
        for key in stale:
            self._events.pop(key, None)


class RequestProtectionMiddleware:
    """Low-cardinality, process-local request protection for the API boundary."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        max_concurrent_requests: int,
        rate_limit_requests: int,
        rate_limit_window_seconds: float,
        trust_forwarded_for: bool,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_concurrent_requests = max_concurrent_requests
        self.trust_forwarded_for = trust_forwarded_for
        self._rate_limiter = SlidingWindowRateLimiter(
            requests=rate_limit_requests,
            window_seconds=rate_limit_window_seconds,
        )
        self._in_flight = 0
        self._capacity_lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        if path.startswith("/health/") or path == "/metrics":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._reject(send, 413, "Request body too large")
                    return
            except ValueError:
                await self._reject(send, 400, "Invalid Content-Length")
                return

        allowed, retry_after = await self._rate_limiter.allow(self._client_key(scope, headers))
        if not allowed:
            await self._reject(
                send,
                429,
                "Rate limit exceeded",
                extra_headers=[(b"retry-after", str(retry_after).encode("ascii"))],
            )
            return

        if not await self._acquire_capacity():
            await self._reject(send, 503, "Server is busy")
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        async def secured_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (
                            b"permissions-policy",
                            b"camera=(), microphone=(), geolocation=()",
                        ),
                    ]
                )
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, limited_receive, secured_send)
        except RequestBodyTooLarge:
            if not response_started:
                await self._reject(send, 413, "Request body too large")
        finally:
            await self._release_capacity()

    async def _acquire_capacity(self) -> bool:
        async with self._capacity_lock:
            if self._in_flight >= self.max_concurrent_requests:
                return False
            self._in_flight += 1
            return True

    async def _release_capacity(self) -> None:
        async with self._capacity_lock:
            self._in_flight = max(0, self._in_flight - 1)

    def _client_key(self, scope: Scope, headers: dict[bytes, bytes]) -> str:
        authorization = headers.get(b"authorization", b"")
        if authorization.lower().startswith(b"bearer "):
            token = authorization[7:].strip()
            digest = hashlib.sha256(token).hexdigest()[:24]
            return f"bearer:{digest}"

        if self.trust_forwarded_for:
            forwarded = headers.get(b"x-forwarded-for")
            if forwarded:
                address = forwarded.split(b",", 1)[0].strip().decode("ascii", errors="ignore")
                if address:
                    return f"ip:{address[:64]}"

        client = scope.get("client")
        host = str(client[0]) if client else "unknown"
        return f"ip:{host[:64]}"

    @staticmethod
    async def _reject(
        send: Send,
        status_code: int,
        detail: str,
        *,
        extra_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        body = (f'{{"detail":"{detail}"}}').encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
        ]
        if extra_headers:
            headers.extend(extra_headers)
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})
