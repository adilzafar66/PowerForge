"""Isolated PostgreSQL/Redis/MinIO extraction through real prefork workers and HTTP."""

import json
import os
import signal
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from statistics import mean, median
from threading import Event, Lock, Thread
from time import monotonic, sleep
from uuid import UUID, uuid4

import pymupdf
import pytest
from celery import Celery
from sqlalchemy import select, text

from celery_integration_support import copy_source, live_worker, wait_for
from powerforge_document_classification.enqueue import CLASSIFY_RUN_TASK
from powerforge_extraction.controls import RunExecution, UnitExecution
from powerforge_extraction.enqueue import CeleryExtractionEnqueue
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.operation_models import ExtractionOperation
from powerforge_extraction.orchestration import ACTIVE, ExtractionCoordinator
from powerforge_extraction.publication_records import Candidate, Fragment
from powerforge_extraction.response_audit import ResponseAudit
from powerforge_extraction.stage_execution import StageResult
from test_extraction_operations import (
    detail_operation,
    new_source,
    preparation,
    reviewed,
    start_operation,
)
from test_extraction_operations import operation_context as operation_context

pytestmark = pytest.mark.integration
RECOGNITION = "EQUIPMENT_RECOGNITION"
ATTRIBUTES = "ATTRIBUTE_EXTRACTION"


class ProviderFixture:
    def __init__(self, action):
        self.action = action
        self.calls = []
        self.lock = Lock()

    def handle(self, body, unit_id):
        wire = json.loads(body["input"][0]["content"][0]["text"])
        owner = wire["page"]["owner"]
        page = owner["page_number"]
        stage = wire["stage"]
        with self.lock:
            call = {
                "id": unit_id,
                "stage": stage,
                "page": page,
                "document": owner["document_id"],
                "start": monotonic(),
            }
            self.calls.append(call)
        status = self.action(call)
        if status == 200:
            if stage == RECOGNITION:
                output = {
                    "stage": stage,
                    "version": wire["version"],
                    "page_context_hash": wire["page_context_hash"],
                    "equipment": [
                        {
                            "local_ref": f"equipment-{page}",
                            "source_description": f"Transformer page {page}",
                            "registry_type": "TWO_WINDING_TRANSFORMER",
                            "tag_state": "ABSENT",
                            "tag": None,
                            "qualification": "UNKNOWN",
                            "raw_qualification": None,
                            "evidence": [],
                        }
                    ],
                }
            else:
                assert [item["local_ref"] for item in wire["upstream"]["equipment"]] == [
                    f"equipment-{page}"
                ]
                output = {
                    "attributes": [
                        {
                            "origin": "EXTRACTED",
                            "equipment_ref": f"equipment-{page}",
                            "association": "ASSERTED",
                            "attribute_key": "primary_voltage",
                            "raw_label": "Primary voltage",
                            "raw_value": str(600 + page),
                            "raw_unit": "V",
                            "value_form": "SINGLE",
                            "qualifiers": [],
                            "proposed_value": str(600 + page),
                            "alternate_representations": [],
                            "proposed_unit": "V",
                            "evidence": [
                                {"kind": "QUOTE", "role": "VALUE", "quote": str(600 + page)}
                            ],
                        }
                    ],
                    "raw_unmapped": [],
                }
            result = {
                "id": unit_id,
                "status": "completed",
                "usage": {"input_tokens": 1000, "output_tokens": 100},
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(output)}],
                    }
                ],
            }
        else:
            result = {"error": {"message": "Simulated rate limit", "code": "rate_limit_exceeded"}}
        if status == 200:
            call["output_sha256"] = sha256(
                result["output"][0]["content"][0]["text"].encode()
            ).hexdigest()
        call.update(end=monotonic(), status=status)
        return status, result

    @contextmanager
    def serve(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                assert self.path == "/v1/responses"
                assert self.headers["Authorization"] == "Bearer offline-test-only"
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                status, result = fixture.handle(body, self.headers["X-Client-Request-Id"])
                payload = json.dumps(result).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield f"http://127.0.0.1:{server.server_port}"
            finally:
                server.shutdown()
                thread.join(timeout=5)


def configure(ctx, *, per_run=2, timeout=100, lease=6):
    fields = {
        "extraction_attribute_input_version": "compact-page-v1",
        "extraction_attribute_prompt_variant": "core-catalog-v1",
        "extraction_attribute_output_version": "server-owned-assertions-v1",
        "extraction_attribute_reasoning_effort": "medium",
        "extraction_use_fake_provider": False,
        "extraction_external_enabled": True,
        "extraction_max_concurrent_per_run": per_run,
        "extraction_max_concurrent_global": 4,
        "extraction_timeout_seconds": timeout,
        "extraction_lease_seconds": lease,
        "openai_api_key": "offline-test-only",
    }
    for key, value in fields.items():
        setattr(ctx["settings"], key, value)
    return {
        **{key.upper(): str(value) for key, value in fields.items()},
        "ENRICHMENT_ENABLED": "true",
        "ENRICHMENT_WORKER_ONLY": "false",
        "ENRICHMENT_OCR_CONFIGURATION": ctx["settings"].enrichment_ocr_configuration,
        "EXTRACTION_BACKOFF_SECONDS": str(ctx["settings"].extraction_backoff_seconds),
    }


def prepare_document(ctx, storage, pages, name="parallel.pdf"):
    existing = set(ctx["storage"].objects)
    with pymupdf.open() as document:
        for number in range(1, pages + 1):
            page = document.new_page(width=360, height=260)
            page.insert_text((40, 90), name)
            page.insert_text((40, 65), f"Transformer {number}   Primary voltage   {600 + number} V")
        source = new_source(ctx, name, document.tobytes())
    source["pages"] = list(range(1, pages + 1))
    preparation(ctx, source)
    copy_source(ctx, storage, skip=existing)
    return source


def admit(ctx, source):
    _, request = reviewed(ctx, [source], mode="reextract")
    reply = start_operation(ctx, request)
    assert reply.status_code == 202, reply.text
    return reply.json()["id"]


def run_for(ctx, operation):
    extraction = detail_operation(ctx, operation)["items"][0]["extraction"]
    return UUID(extraction["run_id"]) if extraction and extraction.get("run_id") else None


def completed(ctx, operation):
    run_id = run_for(ctx, operation)
    if run_id:
        with ctx["factory"]() as session:
            if session.get(ExtractionRun, run_id).status not in ACTIVE:
                return run_id
    return None


def workers(ctx, storage, directory, origin, env, slots, *, beat=True, broker_prefix=None):
    return live_worker(
        ctx,
        storage,
        directory,
        beat=beat,
        app_module="extraction_parallel_worker",
        extra_env={**env, "EXTRACTION_TEST_PROVIDER_ORIGIN": origin, "PGAPPNAME": "pf-e-prefork"},
        queue="document_classification,document_extraction",
        pool="prefork",
        slots=slots,
        broker_prefix=broker_prefix,
    )


def work_id(ctx, run_id, stage, page):
    with ctx["factory"]() as session:
        return next(
            row.id
            for row in session.scalars(
                select(ExtractionWorkUnit).where(
                    ExtractionWorkUnit.run_id == run_id,
                    ExtractionWorkUnit.stage == stage,
                )
            )
            if row.page_numbers == [page]
        )


def verify_publication(ctx, storage, run_id, pages, calls):
    original_digests = {call["id"]: call["output_sha256"] for call in calls}
    with ctx["factory"]() as session:
        run = session.get(ExtractionRun, run_id)
        assert run.status == "COMPLETED" and run.pages_processed == pages
        control = session.get(RunExecution, run_id)
        assert control.calls_admitted == 2 * pages
        units = list(
            session.scalars(select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id))
        )
        assert len(units) == 2 * pages
        published = list(session.scalars(select(StageResult).where(StageResult.run_id == run_id)))
        stage_by_id = {row.work_unit_id: row for row in published}
        units_by_id = {row.id: row for row in units}
        assert len(stage_by_id) == 2 * pages
        attr_ids = set()
        for row in published:
            if row.stage != ATTRIBUTES:
                continue
            attr_ids.add(row.work_unit_id)
            parent = stage_by_id[row.upstream_work_unit_id]
            assert parent.document_page_id == row.document_page_id
            assert parent.result_hash == row.upstream_hash
            assert parent.page_context_hash == row.page_context_hash
            assert (
                units_by_id[parent.work_unit_id].finished_at
                <= units_by_id[row.work_unit_id].started_at
            )
            audit = session.get(ResponseAudit, row.work_unit_id)
            assert audit.request_hash == row.request_hash and audit.accepted == 1
            assert audit.output_sha256 == original_digests[str(row.work_unit_id)]
            with closing(storage.get(audit.object_key)) as stream:
                assert sha256(stream.read()).hexdigest() == audit.output_sha256
            candidate = session.scalar(
                select(Candidate).where(Candidate.work_unit_id == row.work_unit_id)
            )
            assert candidate.local_ref == "attr-0"
            assert candidate.raw_value == str(600 + units_by_id[row.work_unit_id].page_numbers[0])
            assert candidate.document_page_id == row.document_page_id
            fragment = session.scalar(
                select(Fragment).where(Fragment.work_unit_id == row.work_unit_id)
            )
            assert fragment.document_page_id == row.document_page_id
            assert candidate.equipment_id is not None
            assert (
                session.get(Candidate, candidate.equipment_id).work_unit_id == parent.work_unit_id
            )
        assert len(attr_ids) == pages
        assert Counter(call["id"] for call in calls) == Counter(str(unit.id) for unit in units)


def overlap(calls):
    events = sorted(
        (call[key], delta) for call in calls for key, delta in (("start", 1), ("end", -1))
    )
    active = peak = 0
    for _, delta in events:
        active += delta
        peak = max(active, peak)
    return peak


def log_records(directory):
    path = directory / "worker.log"
    return [
        json.loads(line)
        for line in path.read_text().splitlines(keepends=True)
        if line.startswith("{") and line.endswith("\n")
    ]


def verify_processes(directory, slots):
    logs = log_records(directory)
    connections = [m for m in logs if m["message"] == "benchmark db connect"]
    by_process = {m["worker_pid"] for m in connections}
    assert len(by_process) == slots
    owners = {}
    for record in connections:
        backend, pid = record["backend_pid"], record["worker_pid"]
        assert owners.setdefault(backend, pid) == pid
    return logs


def test_two_slots_overlap_and_run_periodic_recovery(
    operation_context, s3_scratch_storage, tmp_path
):
    ctx, storage = operation_context, s3_scratch_storage
    env = configure(ctx)
    source = prepare_document(ctx, storage, 2)
    both = Event()
    release = Event()
    attribute_started = Event()

    def action(call):
        if call["stage"] == ATTRIBUTES:
            attribute_started.set()
        elif call["page"] == 2:
            both.set()
            assert release.wait(15)
        else:
            assert both.wait(10)
            sleep(2.2)
        return 200

    provider = ProviderFixture(action)
    directory = tmp_path / "overlap"
    with provider.serve() as origin, workers(ctx, storage, directory, origin, env, 2):
        operation = admit(ctx, source)
        try:
            assert attribute_started.wait(15), detail_operation(ctx, operation)
            assert any(
                c["stage"] == RECOGNITION and c["page"] == 2 and "end" not in c
                for c in provider.calls
            )
        finally:
            release.set()
        run_id = wait_for(lambda operation=operation: completed(ctx, operation), 20)
    verify_publication(ctx, storage, run_id, 2, provider.calls)
    assert overlap(provider.calls) == 2
    logs = verify_processes(directory, 2)
    assert any(m["message"] == "extraction heartbeat renewed" for m in logs)
    recovery = [m for m in logs if m.get("task_name") == "document_extraction.reconcile"]
    assert any(
        m["message"] == "benchmark task end" and m["monotonic_at"] > provider.calls[1]["start"]
        for m in recovery
    )


def test_concurrent_retry_redelivery_and_timeout(operation_context, s3_scratch_storage, tmp_path):
    ctx, storage = operation_context, s3_scratch_storage
    env = configure(ctx, timeout=4)
    source = prepare_document(ctx, storage, 3)
    rate_limited = False
    waiting = Event()
    release = Event()

    def action(call):
        nonlocal rate_limited
        if call["stage"] == ATTRIBUTES and call["page"] == 1 and not rate_limited:
            rate_limited = True
            return 429
        if call["stage"] == ATTRIBUTES and call["page"] == 3:
            sleep(4.4)
        elif call["stage"] == RECOGNITION and call["page"] == 2:
            waiting.set()
            assert release.wait(3)
        else:
            sleep(0.3)
        return 200

    provider = ProviderFixture(action)
    directory = tmp_path / "retry-timeout"
    with provider.serve() as origin, workers(ctx, storage, directory, origin, env, 2):
        operation = admit(ctx, source)
        try:
            assert waiting.wait(12)
            run_id = wait_for(lambda: run_for(ctx, operation))
            duplicate = work_id(ctx, run_id, RECOGNITION, 2)
            CeleryExtractionEnqueue().enqueue(duplicate)
        finally:
            release.set()
        assert wait_for(lambda operation=operation: completed(ctx, operation), 22) == run_id
    assert rate_limited
    with ctx["factory"]() as session:
        run = session.get(ExtractionRun, run_id)
        assert run.status == "PARTIALLY_COMPLETED" and run.pages_processed == 2
        outcomes = [
            (unit.page_numbers, unit.stage, unit.status, unit.error_code)
            for unit in session.scalars(
                select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id == run_id)
            )
        ]
        assert ([3], ATTRIBUTES, "FAILED", "EXTRACTION_PROVIDER_OUTCOME_UNKNOWN") in outcomes
        assert ([1], ATTRIBUTES, "FAILED", "PROVIDER_RATE_LIMITED") in outcomes
        assert ([1], ATTRIBUTES, "COMPLETED", None) in outcomes
        assert session.get(RunExecution, run_id).calls_admitted == 7
        assert (
            len(list(session.scalars(select(StageResult).where(StageResult.run_id == run_id)))) == 5
        )
    assert len(provider.calls) == 7 and sum(c["id"] == str(duplicate) for c in provider.calls) == 1


def test_global_limit_across_three_runs(operation_context, s3_scratch_storage, tmp_path):
    ctx, storage = operation_context, s3_scratch_storage
    env = configure(ctx)
    sources = [
        prepare_document(ctx, storage, count, f"global-{i}.pdf")
        for i, count in enumerate((2, 2, 1))
    ]
    release = Event()

    def action(call):
        if call["stage"] == RECOGNITION:
            assert release.wait(18)
        return 200

    provider = ProviderFixture(action)
    with (
        provider.serve() as origin,
        workers(ctx, storage, tmp_path / "global-a", origin, env, 2),
        workers(ctx, storage, tmp_path / "global-b", origin, env, 2, beat=False),
    ):
        operations = [admit(ctx, source) for source in sources]
        try:
            wait_for(lambda: len(provider.calls) == 4, 15)
            runs = [wait_for(lambda op=op: run_for(ctx, op)) for op in operations]
            with ctx["factory"].begin() as session:
                statements = select(ExtractionWorkUnit).where(ExtractionWorkUnit.run_id.in_(runs))
                units = list(session.scalars(statements))
                assert sum(u.status == "RUNNING" for u in units) == 4
                pending = next(u for u in units if u.stage == RECOGNITION and u.status == "PENDING")
                # Make a fifth claimant compete even though all four worker slots are full.
                assert ExtractionCoordinator(session, ctx["settings"]).claim(pending.id) is None
                assert session.get(ExtractionWorkUnit, pending.id).started_at is None
        finally:
            release.set()
        for operation in operations:
            wait_for(lambda operation=operation: completed(ctx, operation), 20)
    assert overlap(provider.calls) == 4
    for run_id, source in zip(runs, sources, strict=True):
        with ctx["factory"]() as session:
            document = str(session.get(ExtractionRun, run_id).document_id)
        verify_publication(
            ctx,
            storage,
            run_id,
            len(source["pages"]),
            [call for call in provider.calls if call["document"] == document],
        )


@pytest.mark.parametrize("expire", [False, True])
def test_same_run_lock_wait_and_lease_fencing(
    operation_context, s3_scratch_storage, tmp_path, expire
):
    ctx, storage = operation_context, s3_scratch_storage
    env = configure(ctx, lease=3)
    source = prepare_document(ctx, storage, 2)
    release = Event()

    def action(call):
        if call["stage"] == ATTRIBUTES:
            assert release.wait(15)
        return 200

    provider = ProviderFixture(action)
    directory = tmp_path / "row-lock"
    with provider.serve() as origin, workers(ctx, storage, directory, origin, env, 2):
        operation = admit(ctx, source)
        try:
            wait_for(lambda: sum(c["stage"] == ATTRIBUTES for c in provider.calls) == 2, 15)
            run_id = wait_for(lambda: run_for(ctx, operation))
            with ctx["factory"].begin() as blocker:
                pid = blocker.scalar(text("SELECT pg_backend_pid()"))
                blocker.scalar(
                    select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
                )

                def locked():
                    with ctx["factory"]() as observer:
                        return observer.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE :pid = ANY(pg_blocking_pids(pid))"
                            ),
                            {"pid": pid},
                        )

                wait_for(locked, 3)
                sleep(3.1 if expire else 0.3)
            if not expire:
                wait_for(
                    lambda: any(
                        m["message"] == "extraction heartbeat renewed"
                        and m["heartbeat_db_ms"] >= 250
                        for m in log_records(directory)
                    ),
                    5,
                )
        finally:
            release.set()
        assert wait_for(lambda operation=operation: completed(ctx, operation), 20) == run_id
    logs = log_records(directory)
    denials = [m for m in logs if m["message"] == "extraction lease denied"]
    if expire:
        assert any(m["lease_reason"] == "LEASE_EXPIRED" for m in denials)
    else:
        assert not denials
    if not expire:
        verify_publication(ctx, storage, run_id, 2, provider.calls)
        return
    with ctx["factory"]() as session:
        units = list(
            session.scalars(
                select(ExtractionWorkUnit).where(
                    ExtractionWorkUnit.run_id == run_id, ExtractionWorkUnit.stage == ATTRIBUTES
                )
            )
        )
        assert len(units) == 2
        for unit in units:
            assert unit.error_code == "EXTRACTION_PROVIDER_OUTCOME_UNKNOWN"
            assert session.get(StageResult, unit.id) is None
            assert session.get(ResponseAudit, unit.id) is None


def test_worker_killed_after_dispatch_recovers_without_resend(
    operation_context,
    s3_scratch_storage,
    tmp_path,
):
    ctx, storage = operation_context, s3_scratch_storage
    env = configure(ctx, lease=3)
    source = prepare_document(ctx, storage, 2)
    release = Event()

    def action(call):
        if call["stage"] == RECOGNITION and call["page"] == 1:
            assert release.wait(20)
        return 200

    provider = ProviderFixture(action)
    directory = tmp_path / "lost-child"
    with provider.serve() as origin:
        try:
            with workers(ctx, storage, directory, origin, env, 2):
                operation = admit(ctx, source)
                lost_call = wait_for(
                    lambda: next(
                        (c for c in provider.calls if c["stage"] == RECOGNITION and c["page"] == 1),
                        None,
                    ),
                    15,
                )
                started = next(
                    m
                    for m in log_records(directory)
                    if m.get("unit_id") == lost_call["id"]
                    and m["message"] == "benchmark task start"
                )
                os.kill(started["worker_pid"], signal.SIGKILL)
            with workers(ctx, storage, tmp_path / "replacement", origin, env, 2):
                run_id = wait_for(lambda operation=operation: completed(ctx, operation), 20)
        finally:
            release.set()
    with ctx["factory"]() as session:
        unit = session.get(ExtractionWorkUnit, UUID(lost_call["id"]))
        assert unit.error_code == "EXTRACTION_PROVIDER_OUTCOME_UNKNOWN"
        assert session.get(StageResult, unit.id) is None
        assert session.get(ExtractionRun, run_id).pages_processed == 1
    assert sum(c["page"] == 1 for c in provider.calls) == 1


@contextmanager
def sample_database(ctx):
    stop = Event()
    samples = []

    def observe():
        while not stop.is_set():
            with ctx["factory"]() as session:
                samples.append(
                    tuple(
                        session.execute(
                            text("""
                    SELECT count(*) FILTER (WHERE backend_type='client backend'),
                           count(*) FILTER (WHERE application_name='pf-e-prefork'),
                           count(*) FILTER (WHERE application_name='pf-e-prefork'
                                            AND state='idle in transaction'),
                           count(*) FILTER (WHERE wait_event_type='Lock')
                    FROM pg_stat_activity WHERE pid <> pg_backend_pid()
                """)
                        ).one()
                    )
                )
            stop.wait(0.1)

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(observe)
        try:
            yield samples
        finally:
            stop.set()
            task.result(timeout=5)


def benchmark_metrics(ctx, operation, run_id, count, provider, logs, samples, slots, wall, end):
    waits = {RECOGNITION: [], ATTRIBUTES: []}
    dispatches = {}
    with ctx["factory"]() as session:
        run = session.get(ExtractionRun, run_id)
        op = session.get(ExtractionOperation, UUID(operation))
        seconds = (run.finished_at - op.created_at).total_seconds()
        config = session.get(RunExecution, run_id).configuration
        rows = session.execute(
            select(ExtractionWorkUnit, UnitExecution, StageResult)
            .join(UnitExecution, UnitExecution.work_unit_id == ExtractionWorkUnit.id)
            .join(StageResult, StageResult.work_unit_id == ExtractionWorkUnit.id)
            .where(ExtractionWorkUnit.run_id == run_id)
        ).all()
        by_id = {unit.id: unit for unit, _, _ in rows}
        for unit, delivery, result in rows:
            ready = delivery.available_at
            if result.upstream_work_unit_id:
                ready = max(ready, by_id[result.upstream_work_unit_id].finished_at)
            waits[unit.stage].append(max(0, (unit.started_at - ready).total_seconds() * 1000))
            dispatches[f"{unit.stage}:{unit.page_numbers[0]}"] = delivery.provider_request_hash
    started = {
        m["task_id"]: m["monotonic_at"]
        for m in logs
        if m["message"] == "benchmark task start" and m["monotonic_at"] < end
    }
    completed = {
        m["task_id"]: m["monotonic_at"] for m in logs if m["message"] == "benchmark task end"
    }
    used = sum(
        max(0, min(completed.get(key, end), end) - max(at, wall)) for key, at in started.items()
    )
    beats = [m for m in logs if m["message"] == "extraction heartbeat renewed"]
    assert beats and not any(m["message"] == "extraction lease denied" for m in logs)
    recoveries = [
        m["monotonic_at"]
        for m in logs
        if m.get("task_name") == "document_extraction.reconcile"
        and m["message"] == "benchmark task end"
        and wall < m["monotonic_at"] < end
    ]
    assert recoveries
    checkpoints = [wall, *sorted(recoveries), end]
    return (
        config,
        dispatches,
        {
            "slots": slots,
            "seconds": seconds,
            "pages_per_minute": round(60 * count / seconds, 2),
            "overlap": overlap(provider.calls),
            "worker_utilization": round(used / (slots * (end - wall)), 3),
            "queue_median_ms": {stage: round(median(values), 2) for stage, values in waits.items()},
            "beats": len(beats),
            "max_wakeup_ms": max(m["heartbeat_schedule_delay_ms"] for m in beats),
            "max_renewal_ms": max(m["heartbeat_db_ms"] for m in beats),
            "db_max_connections": max(s[0] for s in samples),
            "db_max_worker_connections": max(s[1] for s in samples),
            "db_max_worker_idle_transaction": max(s[2] for s in samples),
            "db_samples_with_lock_wait": sum(s[3] > 0 for s in samples),
            "median_wakeup_ms": median(m["heartbeat_schedule_delay_ms"] for m in beats),
            "median_renewal_ms": median(m["heartbeat_db_ms"] for m in beats),
            "recovery_max_gap_s": round(
                max(b - a for a, b in zip(checkpoints[:-1], checkpoints[1:], strict=True)), 2
            ),
            "recovery_completed": len(recoveries),
        },
    )


@pytest.mark.skipif(
    os.getenv("RUN_EXTRACTION_BENCHMARK") != "1",
    reason="Set RUN_EXTRACTION_BENCHMARK=1 after the two-slot correctness tests",
)
def test_matched_prefork_benchmark(operation_context, s3_scratch_storage, tmp_path):
    ctx, storage = operation_context, s3_scratch_storage
    count = 10
    configure(ctx)
    prepared_at = monotonic()
    source = prepare_document(ctx, storage, count)
    print(json.dumps({"shared_preparation_seconds": round(monotonic() - prepared_at, 2)}))
    metrics = []
    pinned = None
    for repeat, order in enumerate(((1, 2, 4), (2, 4, 1), (4, 1, 2)), 1):
        for slots in order:
            env = configure(ctx, per_run=4 if slots == 4 else 2)

            def action(call):
                sleep(1.15 if call["stage"] == RECOGNITION else 2.35)
                return 200

            provider = ProviderFixture(action)
            directory = tmp_path / f"benchmark-{repeat}-{slots}"
            with (
                provider.serve() as origin,
                workers(
                    ctx,
                    storage,
                    directory,
                    origin,
                    env,
                    slots,
                    broker_prefix=f"pf-e-{uuid4().hex}:",
                ),
                sample_database(ctx) as samples,
            ):
                wall = monotonic()
                operation = admit(ctx, source)
                run_id = wait_for(lambda operation=operation: completed(ctx, operation), 80)
                end = monotonic()
            verify_publication(ctx, storage, run_id, count, provider.calls)
            config, dispatches, result = benchmark_metrics(
                ctx,
                operation,
                run_id,
                count,
                provider,
                verify_processes(directory, slots),
                samples,
                slots,
                wall,
                end,
            )
            assert config.pop("max_concurrent") == (4 if slots == 4 else 2)
            if pinned is None:
                pinned = config, dispatches
            assert pinned == (config, dispatches)
            assert result["overlap"] == slots
            metrics.append(dict(result, repeat=repeat))
            print(json.dumps(metrics[-1]), flush=True)
    medians = {
        slots: median(r["seconds"] for r in metrics if r["slots"] == slots) for slots in (1, 2, 4)
    }
    assert medians[2] < medians[1]
    for slots, seconds in medians.items():
        print(
            json.dumps(
                {
                    "summary_slots": slots,
                    "seconds": seconds,
                    "speedup": medians[1] / seconds,
                    "efficiency": medians[1] / seconds / slots,
                    "mean_worker_utilization": mean(
                        r["worker_utilization"] for r in metrics if r["slots"] == slots
                    ),
                }
            ),
            flush=True,
        )


def test_shared_worker_leaves_progress_with_classification_active(
    operation_context,
    s3_scratch_storage,
    tmp_path,
):
    ctx, storage = operation_context, s3_scratch_storage
    release = tmp_path / "release-classification"
    env = {**configure(ctx), "EXTRACTION_TEST_CLASSIFICATION_RELEASE": str(release)}
    prefix = f"pf-e-{uuid4().hex}:"
    source = prepare_document(ctx, storage, 1)

    def action(_):
        sleep(0.2)
        return 200

    provider = ProviderFixture(action)
    directory = tmp_path / "shared-queues"
    with (
        provider.serve() as origin,
        workers(ctx, storage, directory, origin, env, 2, broker_prefix=prefix),
    ):
        broker = Celery("parallel-classification-test", broker=ctx["settings"].redis_url)
        broker.conf.broker_transport_options = {"global_keyprefix": prefix}
        task = broker.send_task(
            CLASSIFY_RUN_TASK, args=[str(uuid4())], queue="document_classification", retry=False
        )
        try:
            started = wait_for(
                lambda: next(
                    (
                        m["monotonic_at"]
                        for m in log_records(directory)
                        if m.get("task_id") == task.id and m["message"] == "benchmark task start"
                    ),
                    None,
                )
            )
            operation = admit(ctx, source)
            run_id = wait_for(lambda: completed(ctx, operation), 15)
        finally:
            release.touch()
        finished = wait_for(
            lambda: next(
                (
                    m["monotonic_at"]
                    for m in log_records(directory)
                    if m.get("task_id") == task.id and m["message"] == "benchmark task end"
                ),
                None,
            )
        )
    assert all(started < call["start"] < call["end"] < finished for call in provider.calls)
    verify_publication(ctx, storage, run_id, 1, provider.calls)


def test_parallel_transport_rejects_non_fixture_urls():
    # Import the test app in its own process so patches cannot affect other tests.
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import httpx
from extraction_parallel_worker import loopback_request
for url in ("https://api.openai.com/v1/responses", "http://127.0.0.1:7011/v1/responses",
            "http://127.0.0.1:7010/v1/other"):
    try:
        loopback_request(httpx.Request("POST", url), 7010)
    except AssertionError:
        continue
    raise AssertionError("Test guard allowed unapproved traffic")
loopback_request(httpx.Request("POST", "http://127.0.0.1:7010/v1/responses"), 7010)
""",
        ],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        check=True,
        timeout=10,
    )
