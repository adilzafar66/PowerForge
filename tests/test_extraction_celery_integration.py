"""Real subprocess Celery/beat, Redis transport, PostgreSQL and scratch MinIO.

Uses only the explicitly configured integration services; never calls OpenAI.
"""

import os
import subprocess
import sys
import time
import tomllib
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from celery import Celery

from extraction_execution_support import execution_ctx as execution_ctx

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]


def wait_for(check, seconds=25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = check()
        if result:
            return result
        time.sleep(0.1)
    pytest.fail("Timed out waiting for asynchronous extraction state")


@contextmanager
def live_worker(
    ctx,
    storage,
    directory,
    *,
    beat,
    app_module="extraction_worker.celery_app",
    extra_env=None,
    queue="document_extraction",
):
    directory.mkdir(exist_ok=True)
    name = f"phase6b-{uuid4().hex[:8]}@localhost"
    paths = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"][
        "pythonpath"
    ]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(str(ROOT / p) for p in [*paths, "tests"]),
        "DATABASE_URL": ctx["settings"].database_url,
        "REDIS_URL": ctx["settings"].redis_url,
        "S3_ENDPOINT_URL": ctx["settings"].s3_endpoint_url,
        "S3_BUCKET": storage.bucket,
        "AI_CLASSIFICATION_ENABLED": "false",
        "AI_PROVIDER": "fake",
        "EXTRACTION_EXTERNAL_ENABLED": "false",
        "EXTRACTION_RECOVERY_INTERVAL_SECONDS": "1",
        "EXTRACTION_REDISPATCH_SECONDS": "1",
        **(extra_env or {}),
    }
    worker_log = (directory / "worker.log").open("w+")
    scheduler_log = (directory / "beat.log").open("w+")
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            app_module,
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "-Q",
            queue,
            "--hostname",
            name,
            "--without-gossip",
            "--without-mingle",
            "--loglevel=WARNING",
        ],
        cwd=ROOT,
        env=env,
        stdout=worker_log,
        stderr=subprocess.STDOUT,
    )
    scheduler = None
    try:
        broker = Celery("extraction-integration-control", broker=ctx["settings"].redis_url)
        wait_for(lambda: broker.control.ping(destination=[name], timeout=0.5))
        if beat:
            scheduler = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    app_module,
                    "beat",
                    "--loglevel=WARNING",
                    f"--schedule={directory / 'schedule'}",
                ],
                cwd=ROOT,
                env=env,
                stdout=scheduler_log,
                stderr=subprocess.STDOUT,
            )
        yield worker
    finally:
        for process in [scheduler, worker]:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        worker_log.close()
        scheduler_log.close()


def copy_source(ctx, storage):
    for key, obj in ctx["storage"].objects.items():
        storage.put(key, BytesIO(obj.data), len(obj.data), obj.content_type)
