import structlog
from prometheus_client import start_http_server

logger = structlog.get_logger()


def start_process_metrics_server(port: int, *, process_name: str) -> None:
    if port <= 0:
        return
    start_http_server(port, addr="0.0.0.0")
    logger.info(
        "metrics_server_started",
        process_name=process_name,
        port=port,
    )
