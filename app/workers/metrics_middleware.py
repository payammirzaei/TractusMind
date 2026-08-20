import dramatiq

from app.core.config import get_settings
from app.observability.server import start_process_metrics_server


class WorkerMetricsMiddleware(dramatiq.Middleware):
    """Start the TractusMind metrics server inside the Dramatiq worker subprocess."""

    def after_process_boot(self, broker) -> None:
        settings = get_settings()
        start_process_metrics_server(
            settings.worker_metrics_port,
            process_name="ingestion-worker",
        )
