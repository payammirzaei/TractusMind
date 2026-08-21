from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from opentelemetry import trace
from prometheus_client import Counter, Gauge, Histogram

from app.observability.trace_context import record_stage_duration

HTTP_REQUESTS = Counter(
    "tractusmind_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "tractusmind_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ("method", "route"),
)
PIPELINE_STAGE_DURATION = Histogram(
    "tractusmind_pipeline_stage_duration_seconds",
    "Latency of source-grounded answer pipeline stages.",
    ("stage", "intent"),
)
PIPELINE_STAGE_ERRORS = Counter(
    "tractusmind_pipeline_stage_errors_total",
    "Pipeline stage failures.",
    ("stage", "intent"),
)
ANSWERS = Counter(
    "tractusmind_answers_total",
    "Final answer outcomes.",
    ("intent", "outcome"),
)
FEEDBACK = Counter(
    "tractusmind_answer_feedback_total",
    "User feedback submitted for persisted answers.",
    ("rating",),
)
QUALITY_REVIEW_SIGNALS = Counter(
    "tractusmind_quality_review_signals_total",
    "Production signals successfully routed into the quality-review workflow.",
    ("trigger",),
)
QUALITY_REVIEW_DECISIONS = Counter(
    "tractusmind_quality_review_decisions_total",
    "Human quality-review decisions.",
    ("action", "root_cause"),
)
QUALITY_REGRESSION_PROMOTIONS = Counter(
    "tractusmind_quality_regression_promotions_total",
    "Human-reviewed production interactions promoted to regression cases.",
    ("benchmark_kind",),
)
RETRIEVAL_RESULTS = Histogram(
    "tractusmind_retrieval_results",
    "Number of retrieval results returned before generation.",
    ("intent",),
    buckets=(0, 1, 2, 3, 4, 6, 10, 20, 40, 80),
)
MODEL_LOAD_DURATION = Histogram(
    "tractusmind_model_load_duration_seconds",
    "First-use local model warm-up duration, including lazy initialization.",
    ("role",),
)
MODEL_LOADED = Gauge(
    "tractusmind_model_loaded",
    "Whether a local model has been initialized in this process.",
    ("role",),
)
MODEL_OPERATION_DURATION = Histogram(
    "tractusmind_model_operation_duration_seconds",
    "Local model operation latency.",
    ("role", "operation"),
    buckets=(
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.15,
        0.25,
        0.5,
        0.75,
        1.0,
        1.25,
        1.5,
        1.75,
        2.0,
        2.5,
        5.0,
        10.0,
    ),
)
PROVIDER_REQUESTS = Counter(
    "tractusmind_provider_requests_total",
    "External provider logical request outcomes.",
    ("provider", "operation", "outcome"),
)
PROVIDER_RETRIES = Counter(
    "tractusmind_provider_retries_total",
    "External provider retries by reason.",
    ("provider", "operation", "reason"),
)
PROVIDER_RETRY_DELAY = Histogram(
    "tractusmind_provider_retry_delay_seconds",
    "Delay applied before external provider retries.",
    ("provider", "operation"),
)
PROVIDER_CIRCUIT_OPEN = Counter(
    "tractusmind_provider_circuit_open_total",
    "External provider calls rejected or circuits opened after transient failures.",
    ("provider", "event"),
)
INGESTION_RUNS = Counter(
    "tractusmind_ingestion_runs_total",
    "Background ingestion run outcomes.",
    ("source_id", "status"),
)
INGESTION_DURATION = Histogram(
    "tractusmind_ingestion_duration_seconds",
    "End-to-end background ingestion duration.",
    ("source_id",),
)
INGESTION_FILES = Counter(
    "tractusmind_ingestion_files_total",
    "Files classified by successful incremental ingestion runs.",
    ("source_id", "change"),
)
INGESTION_LOCK_CONTENTION = Counter(
    "tractusmind_ingestion_lock_contention_total",
    "Source sync jobs skipped because another worker owns the source lock.",
    ("source_id",),
)
WORKER_JOBS_IN_PROGRESS = Gauge(
    "tractusmind_worker_jobs_in_progress",
    "Ingestion worker jobs currently executing in this process.",
)
WORKER_JOBS = Counter(
    "tractusmind_worker_jobs_total",
    "Ingestion worker job outcomes.",
    ("status",),
)
QUEUE_ENQUEUED = Counter(
    "tractusmind_queue_enqueued_total",
    "Source sync jobs enqueued by instrumented control paths.",
    ("origin",),
)

_TRACER = trace.get_tracer("tractusmind")


@contextmanager
def observe_stage(stage: str, intent: str = "unknown") -> Iterator[None]:
    started = perf_counter()
    with _TRACER.start_as_current_span(f"tractusmind.{stage}") as span:
        span.set_attribute("tractusmind.stage", stage)
        span.set_attribute("tractusmind.intent", intent)
        try:
            yield
        except Exception:
            PIPELINE_STAGE_ERRORS.labels(stage=stage, intent=intent).inc()
            raise
        finally:
            duration = perf_counter() - started
            PIPELINE_STAGE_DURATION.labels(stage=stage, intent=intent).observe(duration)
            record_stage_duration(stage, duration)


@contextmanager
def observe_model_operation(role: str, operation: str) -> Iterator[None]:
    started = perf_counter()
    try:
        yield
    finally:
        duration = perf_counter() - started
        MODEL_OPERATION_DURATION.labels(role=role, operation=operation).observe(duration)
        record_stage_duration(f"model.{role}.{operation}", duration)


def record_model_load(role: str, duration_seconds: float) -> None:
    MODEL_LOAD_DURATION.labels(role=role).observe(duration_seconds)
    MODEL_LOADED.labels(role=role).set(1)
