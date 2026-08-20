# Provider resilience

TractusMind treats external LLM and GitHub calls as unreliable network boundaries. Provider
resilience is bounded, observable, and deliberately different from business-level retries such as
Dramatiq job retries.

## Retry policy

Transient failures are retried with exponential backoff plus jitter:

```text
attempt 1
  -> transient failure
  -> bounded backoff
attempt 2
  -> transient failure
  -> bounded backoff
attempt N
  -> success OR final provider error
```

Defaults:

```bash
LLM_MAX_ATTEMPTS=3
GITHUB_MAX_ATTEMPTS=4
PROVIDER_RETRY_BASE_SECONDS=0.5
PROVIDER_RETRY_MAX_SECONDS=8
```

Provider `Retry-After` is respected but capped by `PROVIDER_RETRY_MAX_SECONDS`, so a worker does not
sleep indefinitely inside one request. GitHub `X-RateLimit-Reset` is also converted into a bounded
retry delay when present.

## Retryability

LLM retries:

```text
transport errors / timeouts
HTTP 408
HTTP 429
HTTP 500 / 502 / 503 / 504
```

LLM client/auth errors such as `400` and `401` fail immediately.

GitHub retries:

```text
transport errors / timeouts
HTTP 429
HTTP 500 / 502 / 503 / 504
HTTP 403 only when it is identifiable as rate limiting
```

Ordinary GitHub `403`, `404`, and other non-transient client errors fail immediately.

## LLM idempotency

One UUID-backed `Idempotency-Key` is generated for each logical chat-completions call and reused
across every retry of that call.

This allows compatible providers to deduplicate a request when a timeout happens after the POST may
already have reached the provider. TractusMind cannot guarantee deduplication when an arbitrary
OpenAI-compatible provider ignores idempotency keys; the retries remain bounded in that case.

## Circuit breaker

LLM and GitHub use process-shared circuit breakers. Defaults:

```bash
PROVIDER_CIRCUIT_FAILURE_THRESHOLD=3
PROVIDER_CIRCUIT_COOLDOWN_SECONDS=30
```

A logical request counts as one transient failure only after its internal retries are exhausted.
After the failure threshold, the provider circuit opens and new calls fail fast instead of creating
a retry storm.

After cooldown, exactly one half-open probe is admitted in the process:

```text
closed
  -> repeated logical transient failures
open
  -> cooldown
half-open single probe
  -> success -> closed
  -> transient failure -> open
```

The circuit is process-local rather than globally distributed. This is intentional: it protects a
single API/worker process from hammering a failing provider without introducing Redis availability
as a prerequisite for answering questions or fetching sources.

## Interaction with ingestion retries

GitHub retries happen inside one source-sync job. If all bounded provider attempts fail, the source
sync fails normally and Dramatiq can retry the job according to its existing worker retry policy.
The process-shared GitHub circuit remains open across those job invocations in the same worker
process, preventing immediate repeated GitHub pressure.

## Metrics

Prometheus exposes low-cardinality provider metrics:

```text
tractusmind_provider_requests_total{provider,operation,outcome}
tractusmind_provider_retries_total{provider,operation,reason}
tractusmind_provider_retry_delay_seconds{provider,operation}
tractusmind_provider_circuit_open_total{provider,event}
```

No URL path, prompt, response body, API key, request ID, error body, repository path, or source text
is used as a metric label.

Useful outcomes include:

```text
success
http_error
invalid_response
transient_failure
circuit_open
```

Circuit events are:

```text
opened
rejected
```

## Configuration

```bash
GITHUB_TIMEOUT_SECONDS=30
GITHUB_MAX_ATTEMPTS=4
LLM_TIMEOUT_SECONDS=60
LLM_MAX_ATTEMPTS=3
PROVIDER_RETRY_BASE_SECONDS=0.5
PROVIDER_RETRY_MAX_SECONDS=8
PROVIDER_CIRCUIT_FAILURE_THRESHOLD=3
PROVIDER_CIRCUIT_COOLDOWN_SECONDS=30
```

The same GitHub resilience settings are used by the background ingestion worker and direct
`tractusmind-ingest` commands. The LLM settings are applied to both answer generation and the claim
verifier because they share the same provider instance.
