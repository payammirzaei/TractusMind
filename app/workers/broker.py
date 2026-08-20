import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings
from app.workers.metrics_middleware import WorkerMetricsMiddleware

settings = get_settings()
broker = RedisBroker(url=settings.redis_url)
broker.add_middleware(WorkerMetricsMiddleware())
dramatiq.set_broker(broker)
