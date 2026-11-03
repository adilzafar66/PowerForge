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

import httpx
import pytest
from celery import Celery

from documents_support import client
from extraction_execution_support import detail, start_run, units
from extraction_execution_support import execution_ctx as execution_ctx
from powerforge_api.main import app
from powerforge_document_processing.storage.factory import get_object_storage
from powerforge_extraction.controls import UnitExecution
from powerforge_extraction.models import ExtractionWorkUnit

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
def live_worker(ctx, storage, directory, *, beat):
    directory.mkdir(exist_ok=True)
    name = f"phase6b-{uuid4().hex[:8]}@localhost"
    paths = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"][
        "pythonpath"
    ]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(str(ROOT / p) for p in paths),
        "DATABASE_URL": ctx["settings"].database_url,
        "REDIS_URL": ctx["settings"].redis_url,
        "S3_ENDPOINT_URL": ctx["settings"].s3_endpoint_url,
        "S3_BUCKET": storage.bucket,
        "AI_CLASSIFICATION_ENABLED": "false",
        "AI_PROVIDER": "fake",
        "EXTRACTION_EXTERNAL_ENABLED": "false",
        "EXTRACTION_RECOVERY_INTERVAL_SECONDS": "1",
        "EXTRACTION_REDISPATCH_SECONDS": "1",
    }
    worker_log = (directory / "worker.log").open("w+")
    scheduler_log = (directory / "beat.log").open("w+")
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "extraction_worker.celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "-Q",
            "document_extraction",
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
                    "extraction_worker.celery_app",
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


def test_beat_recovers_persisted_but_undelivered_work_and_real_source_access(
    execution_ctx, s3_scratch_storage, tmp_path
):
    ctx = execution_ctx
    copy_source(ctx, s3_scratch_storage)
    # The API transport records a notification but no Redis message is actually sent.
    # A new scheduler/worker process must rediscover the pending DB delivery record.
    rid = start_run(ctx)["run"]["id"]
    assert detail(ctx, rid)["run"]["status"] == "PENDING"
    with live_worker(ctx, s3_scratch_storage, tmp_path / "normal", beat=True):
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
        result = detail(ctx, rid)
        assert result["execution"]["calls_admitted"] == 1
        candidates = client.get(ctx["base"] + f"/runs/{rid}/candidates").json()["items"]
        assert len(candidates) == 1 and candidates[0]["diagnostics"]["synthetic"] is True
        evidence_id = candidates[0]["evidence"][0]["evidence"]["id"]
        previous = app.dependency_overrides[get_object_storage]
        app.dependency_overrides[get_object_storage] = lambda: s3_scratch_storage
        try:
            evidence = client.get(ctx["base"] + f"/evidence/{evidence_id}").json()
            downloaded = httpx.get(evidence["artifact_url"], timeout=5)
            assert downloaded.status_code == 200
            assert downloaded.content.startswith(b"rated 750 kVA")
        finally:
            app.dependency_overrides[get_object_storage] = previous


def test_killed_worker_lease_is_recovered_after_process_restart(
    execution_ctx, s3_scratch_storage, tmp_path
):
    ctx = execution_ctx
    ctx["settings"].extraction_fake_scenario = "slow"
    ctx["settings"].extraction_lease_seconds = 3
    copy_source(ctx, s3_scratch_storage)
    rid = start_run(ctx)["run"]["id"]
    uid = units(ctx, rid)[0]
    with live_worker(ctx, s3_scratch_storage, tmp_path / "crashed", beat=True) as worker:

        def started():
            with ctx["factory"]() as session:
                control = session.get(UnitExecution, uid)
                return (
                    control.provider_started_at is not None
                    and session.get(ExtractionWorkUnit, uid).status == "RUNNING"
                )

        wait_for(started)
        worker.kill()
        worker.wait(timeout=5)
    with live_worker(ctx, s3_scratch_storage, tmp_path / "restarted", beat=True):
        wait_for(lambda: detail(ctx, rid)["run"]["status"] == "COMPLETED")
    result = detail(ctx, rid)
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["status"] == "FAILED"
    assert result["attempts"][0]["error_code"] == "WORKER_INTERRUPTED"
    assert result["attempts"][1]["status"] == "COMPLETED"
    assert result["execution"]["unreported_admissions"] == 1
