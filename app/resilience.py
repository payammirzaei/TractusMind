import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock
from time import monotonic


class CircuitOpenError(RuntimeError):
    pass


class ProviderCircuitBreaker:
    """Process-local circuit breaker with a single half-open probe."""

    def __init__(
        self,
        *,
        provider: str,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._failures = 0
        self._open_until: float | None = None
        self._probe_in_flight = False
        self._lock = Lock()

    async def before_call(self) -> None:
        with self._lock:
            now = self._clock()
            if self._open_until is None:
                return
            if now < self._open_until:
                raise CircuitOpenError(f"{self.provider} circuit is open")
            if self._probe_in_flight:
                raise CircuitOpenError(f"{self.provider} circuit is half-open")
            self._probe_in_flight = True

    async def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = None
            self._probe_in_flight = False

    async def record_transient_failure(self) -> bool:
        """Record a provider availability failure and return whether the circuit opened."""
        with self._lock:
            self._failures += 1
            should_open = self._probe_in_flight or self._failures >= self.failure_threshold
            self._probe_in_flight = False
            if should_open:
                self._open_until = self._clock() + self.cooldown_seconds
            return should_open


_SHARED_BREAKERS: dict[tuple[str, str, int, float], ProviderCircuitBreaker] = {}
_SHARED_BREAKERS_LOCK = Lock()


def shared_provider_circuit(
    *,
    provider: str,
    scope: str,
    failure_threshold: int,
    cooldown_seconds: float,
) -> ProviderCircuitBreaker:
    key = (provider, scope, failure_threshold, cooldown_seconds)
    with _SHARED_BREAKERS_LOCK:
        breaker = _SHARED_BREAKERS.get(key)
        if breaker is None:
            breaker = ProviderCircuitBreaker(
                provider=provider,
                failure_threshold=failure_threshold,
                cooldown_seconds=cooldown_seconds,
            )
            _SHARED_BREAKERS[key] = breaker
    return breaker


def parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return max(0.0, float(normalized))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def backoff_seconds(
    attempt: int,
    *,
    base_seconds: float,
    max_seconds: float,
    retry_after: float | None = None,
    jitter_ratio: float = 0.2,
) -> float:
    if attempt < 1:
        raise ValueError("attempt must be positive")
    if retry_after is not None:
        return min(max_seconds, max(0.0, retry_after))
    exponential = min(max_seconds, base_seconds * (2 ** (attempt - 1)))
    jitter = exponential * jitter_ratio * random.random()
    return min(max_seconds, exponential + jitter)


async def sleep_before_retry(
    attempt: int,
    *,
    base_seconds: float,
    max_seconds: float,
    retry_after: float | None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> float:
    delay = backoff_seconds(
        attempt,
        base_seconds=base_seconds,
        max_seconds=max_seconds,
        retry_after=retry_after,
    )
    await sleep(delay)
    return delay
