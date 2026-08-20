# Observability

TractusMind exposes low-cardinality Prometheus metrics and optional OpenTelemetry traces for the
API, RAG pipeline, local models, ingestion worker, and source scheduler.

## Local topology

`docker compose up --build` starts a pinned Prometheus service at `http://localhost:9090` and
scrapes four targets:

| Target | Endpoint | Purpose |
| --- | --- | --- |
| API | `api:8000/metrics` | HTTP + answer pipeline + API process/model metrics |
| Worker domain | `worker:9101/metrics` | TractusMind ingestion + worker/model metrics |
| Dramatiq | `worker:9191/` | Native queue, retry, error, in-progress, and job-duration metrics |
| Scheduler | `scheduler:9102/metrics` | Scheduled enqueue metrics |

The local scrape configuration is `config/prometheus.yml`.

Dramatiq uses Prometheus multiprocess mode. The worker startup command creates and clears the
multiprocess directory before importing the worker so native Dramatiq metrics remain valid even
though TractusMind also imports `prometheus_client`.

## API metrics security

`/metrics` is available without a key only when `APP_ENV=development`.

In any other environment, configure `METRICS_ADMIN_KEY` or reuse `OPS_ADMIN_KEY` and send:

```http
X-TractusMind-Metrics-Key: <secret>
```

Set `METRICS_ENABLED=false` to disable the API endpoint entirely. Worker and scheduler metrics
ports should remain private-network-only in production.

## TractusMind metrics

Important families include:

- `tractusmind_http_requests_total`
- `tractusmind_http_request_duration_seconds`
- `tractusmind_pipeline_stage_duration_seconds`
- `tractusmind_pipeline_stage_errors_total`
- `tractusmind_answers_total`
- `tractusmind_retrieval_results`
- `tractusmind_model_load_duration_seconds`
- `tractusmind_model_loaded`
- `tractusmind_model_operation_duration_seconds`
- `tractusmind_ingestion_runs_total`
- `tractusmind_ingestion_duration_seconds`
- `tractusmind_ingestion_files_total`
- `tractusmind_ingestion_lock_contention_total`
- `tractusmind_worker_jobs_in_progress`
- `tractusmind_worker_jobs_total`
- `tractusmind_queue_enqueued_total`

Dramatiq additionally exports its native `dramatiq_*` metrics, including processed messages,
errors, retries, in-progress messages, and message duration.

## Cardinality policy

Metric labels are deliberately bounded. Allowed labels include route templates, pipeline stages,
query intent, fixed model roles, source IDs from the allowlisted registry, status, and change type.

Never put these values in metric labels:

- raw URLs or arbitrary paths
- user questions or prompts
- source-code text
- error messages or stack traces
- commit SHAs or chunk IDs
- request IDs or trace IDs
- API keys, authorization headers, or other secrets

Request IDs and trace IDs belong in logs/traces, not metric labels.

## Request correlation

Every non-metrics API response receives `X-Request-ID`. The same request ID is bound into
`structlog` context for request-scoped logs. When an OpenTelemetry server span is active, its trace
ID is also added to log context.

HTTP metrics use the FastAPI route template, for example `/v1/ops/sources/{source_id}`, rather
than the raw request path.

## OpenTelemetry traces

Tracing export is disabled unless a full OTLP/HTTP traces endpoint is configured:

```bash
OTEL_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_SERVICE_NAME=tractusmind-api
OTEL_SAMPLE_RATIO=1.0
```

The API uses a parent-based trace-ID ratio sampler. FastAPI server spans are created automatically,
while TractusMind adds manual child spans for the grounded answer stages:

```text
HTTP request span
  -> tractusmind.retrieval
  -> tractusmind.generation
  -> tractusmind.verification
```

No request/response headers or question bodies are configured for capture. No OTLP endpoint means
no exporter, background thread, or collector dependency at runtime.

## Useful PromQL

P95 HTTP latency by route:

```promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(tractusmind_http_request_duration_seconds_bucket[5m])
  )
)
```

P95 RAG stage latency:

```promql
histogram_quantile(
  0.95,
  sum by (le, stage) (
    rate(tractusmind_pipeline_stage_duration_seconds_bucket[5m])
  )
)
```

Grounded answer rate:

```promql
sum(rate(tractusmind_answers_total{outcome="grounded"}[5m]))
/
sum(rate(tractusmind_answers_total[5m]))
```

Ingestion failures by source:

```promql
sum by (source_id) (
  rate(tractusmind_ingestion_runs_total{status="failed"}[15m])
)
```

Worker lock contention:

```promql
sum by (source_id) (
  rate(tractusmind_ingestion_lock_contention_total[15m])
)
```

Local-model operation P95:

```promql
histogram_quantile(
  0.95,
  sum by (le, role, operation) (
    rate(tractusmind_model_operation_duration_seconds_bucket[5m])
  )
)
```
