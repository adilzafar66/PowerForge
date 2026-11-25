"""Test-only prefork app. The SDK is confined to a loopback HTTP fixture."""

import logging
import os
from importlib import import_module
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlsplit

import httpx
from celery.signals import after_setup_logger, task_postrun, task_prerun
from openai import OpenAI
from sqlalchemy import event

from extraction_worker import extraction_tasks
from extraction_worker.celery_app import _engine
from extraction_worker.celery_app import celery_app as celery_app
from extraction_worker.openai_extraction import OpenAIExtractionProvider
from powerforge_document_classification.enqueue import CLASSIFY_RUN_TASK
from powerforge_document_processing.storage.factory import build_s3_storage
from powerforge_extraction.enqueue import RECOVER_TASK, UNIT_TASK
from powerforge_shared.config import get_settings
from powerforge_shared.logging import JsonFormatter

logger = logging.getLogger(__name__)
if prefix := os.getenv("EXTRACTION_TEST_QUEUE_PREFIX"):
    celery_app.conf.broker_transport_options = {
        **celery_app.conf.broker_transport_options,
        "global_keyprefix": prefix,
    }


@after_setup_logger.connect
def configure_observation(logger, **_):
    for handler in logger.handlers:
        handler.setFormatter(JsonFormatter())
    logging.getLogger("powerforge_extraction.execution").setLevel(logging.DEBUG)


@event.listens_for(_engine(), "connect")
def record_connection(connection, record):
    record.info["creator_pid"] = os.getpid()
    logger.warning(
        "benchmark db connect",
        extra={"worker_pid": os.getpid(), "backend_pid": connection.info.backend_pid},
    )


@event.listens_for(_engine(), "checkout")
def verify_connection_process(connection, record, _proxy):
    if record.info.get("creator_pid") != os.getpid():
        raise AssertionError("Connection inherited across worker processes")


def observe_task(phase, task, task_id, args):
    if task.name in (UNIT_TASK, RECOVER_TASK, CLASSIFY_RUN_TASK):
        logger.warning(
            "benchmark task " + phase,
            extra={
                "task_id": task_id,
                "task_name": task.name,
                "worker_pid": os.getpid(),
                "unit_id": args[0] if args else None,
                "monotonic_at": monotonic(),
            },
        )


@task_prerun.connect
def task_started(task, task_id, args, **_):
    observe_task("start", task, task_id, args)


@task_postrun.connect
def task_finished(task, task_id, args, **_):
    observe_task("end", task, task_id, args)


def loopback_request(request, port):
    if (
        request.url.scheme != "http"
        or request.url.host != "127.0.0.1"
        or request.url.port != port
        or request.url.path != "/v1/responses"
        or request.method != "POST"
    ):
        raise AssertionError("Parallel extraction test blocked a request outside its fixture")


def local_provider(claim):
    origin = urlsplit(os.environ["EXTRACTION_TEST_PROVIDER_ORIGIN"])
    if origin.scheme != "http" or origin.hostname != "127.0.0.1" or not origin.port:
        raise ValueError("Parallel extraction requires an explicit loopback origin")
    transport = httpx.Client(
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [lambda request: loopback_request(request, origin.port)]},
    )
    client = OpenAI(
        api_key="offline-test-only",
        base_url=f"http://127.0.0.1:{origin.port}/v1",
        max_retries=0,
        http_client=transport,
    )
    provider = OpenAIExtractionProvider(get_settings(), claim.profile, client)
    original_execute = provider.execute

    def execute(request):
        try:
            return original_execute(request)
        finally:
            client.close()

    provider.execute = execute
    return provider


_execute = extraction_tasks.execute_unit


def execute_with_scratch_audit(unit_id, factory, storage, settings, provider_factory):
    # Verify the real object I/O and atomic audit insert on the disposable bucket.
    # Restricted audit bucket provisioning and expiry are tested independently.
    return _execute(
        unit_id,
        factory,
        storage,
        settings,
        provider_factory,
        audit_storage=build_s3_storage(settings),
    )


extraction_tasks.provider_for = local_provider
extraction_tasks.execute_unit = execute_with_scratch_audit


if release_path := os.getenv("EXTRACTION_TEST_CLASSIFICATION_RELEASE"):
    # Simulate occupancy through the actual classification task and queue.
    def classification_slot(*_, **__):
        deadline = monotonic() + 25
        while not Path(release_path).exists():
            if monotonic() >= deadline:
                raise TimeoutError("Classification fixture was not released")
            sleep(0.05)

    import_module("extraction_worker.celery_app").execute_classification_run = classification_slot
