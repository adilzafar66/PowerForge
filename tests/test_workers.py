from document_worker.celery_app import heartbeat as document_heartbeat
from extraction_worker.celery_app import heartbeat as extraction_heartbeat
from validation_worker.celery_app import heartbeat as validation_heartbeat


def test_document_worker_heartbeat() -> None:
    assert document_heartbeat() == {"status": "ok", "worker": "document-worker"}


def test_extraction_worker_heartbeat() -> None:
    assert extraction_heartbeat() == {"status": "ok", "worker": "extraction-worker"}


def test_validation_worker_heartbeat() -> None:
    assert validation_heartbeat() == {"status": "ok", "worker": "validation-worker"}
