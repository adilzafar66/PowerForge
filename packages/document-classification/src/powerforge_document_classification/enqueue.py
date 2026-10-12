"""Publish a classification run to the document_classification queue.

This is the only module in the classification package that imports Celery.
"""

from uuid import UUID

from celery import Celery

from powerforge_shared.config import get_settings

CLASSIFY_RUN_TASK = "document_classification.classify_run"
CLASSIFY_RUN_QUEUE = "document_classification"


class CeleryClassificationEnqueue:
    """Sends the classification task by name. The worker owns the task body."""

    def __init__(self, app: Celery | None = None) -> None:
        self._app = app

    def enqueue_document_classification(self, run_id: UUID) -> None:
        self._celery().send_task(
            CLASSIFY_RUN_TASK,
            args=[str(run_id)],
            queue=CLASSIFY_RUN_QUEUE,
        )

    def _celery(self) -> Celery:
        if self._app is None:
            self._app = Celery(
                "powerforge_document_classification",
                broker=get_settings().redis_url,
            )
        return self._app


def get_classification_enqueue() -> CeleryClassificationEnqueue:
    """FastAPI dependency. Tests override this so classification does not need Redis."""
    return CeleryClassificationEnqueue()
