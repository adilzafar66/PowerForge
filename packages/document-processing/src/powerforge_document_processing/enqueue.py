"""Publish a processing run to the document-worker queue.

This is the only module in the package that imports Celery. The API uses it
so it does not import ``document_worker``. The renderer and ``processing.py``
do not import Celery.
"""

from __future__ import annotations

from uuid import UUID

from celery import Celery

from powerforge_shared.config import get_settings

PROCESS_RUN_TASK = "document_processing.process_run"
PROCESS_RUN_QUEUE = "document_processing"


class CeleryProcessingEnqueue:
    """Send one run id to ``document_processing`` by task name."""

    def __init__(self) -> None:
        self._app: Celery | None = None

    def enqueue_document_processing(self, run_id: UUID) -> None:
        self._client().send_task(
            PROCESS_RUN_TASK,
            args=[str(run_id)],
            queue=PROCESS_RUN_QUEUE,
        )

    def _client(self) -> Celery:
        if self._app is None:
            self._app = Celery(
                "powerforge_document_processing",
                broker=get_settings().redis_url,
            )
        return self._app


def get_processing_enqueue() -> CeleryProcessingEnqueue:
    """FastAPI dependency. Tests override this so uploads do not need Redis."""
    return CeleryProcessingEnqueue()
