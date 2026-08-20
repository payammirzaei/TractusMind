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
        MODEL_OPERATION_DURATION.labels(role=role, operation=operation).observe(
            perf_counter() - started
        )


def record_model_load(role: str, duration_seconds: float) -> None:
    MODEL_LOAD_DURATION.labels(role=role).observe(duration_seconds)
    MODEL_LOADED.labels(role=role).set(1)
