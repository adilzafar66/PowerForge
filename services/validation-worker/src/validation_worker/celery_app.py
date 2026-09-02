from celery import Celery

from powerforge_shared.config import get_settings
from powerforge_shared.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

celery_app = Celery(
    "validation_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery_app.task(name="validation_worker.heartbeat")
def heartbeat() -> dict[str, str]:
    return {"status": "ok", "worker": "validation-worker"}
