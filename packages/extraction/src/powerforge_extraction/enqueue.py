"""Bounded Celery notification transport. PostgreSQL delivery records survive failure."""

from uuid import UUID

from celery import Celery

from powerforge_shared.config import get_settings

UNIT_TASK = "document_extraction.execute_unit"
RECOVER_TASK = "document_extraction.reconcile"
QUEUE = "document_extraction"


class CeleryExtractionEnqueue:
    def __init__(self, app: Celery | None = None) -> None:
        self.app = app

    def enqueue(self, unit_id: UUID) -> None:
        if self.app is None:
            self.app = Celery("powerforge_extraction", broker=get_settings().redis_url)
            self.app.conf.update(
                broker_connection_timeout=2,
                broker_transport_options={
                    "socket_connect_timeout": 2,
                    "socket_timeout": 2,
                    "retry_on_timeout": False,
                },
            )
        self.app.send_task(UNIT_TASK, args=[str(unit_id)], queue=QUEUE, retry=False)


def get_extraction_enqueue() -> CeleryExtractionEnqueue:
    return CeleryExtractionEnqueue()
