"""Exercise the debugger against a genuinely published, synthetic partial result."""

import importlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from powerforge_ai.extraction import AttributeOutput, ExecutionUsage
from powerforge_document_processing.storage import InMemoryObjectStorage
from powerforge_extraction.execution import execute_unit
from powerforge_extraction.stage_execution import FakeExtractionProvider
from test_extraction_operations import admitted_page, new_source
from test_extraction_operations import operation_context as operation_context

pytestmark = pytest.mark.integration


def test_debugger_partial_attempt_comparison_and_exact_export(operation_context, monkeypatch):
    ctx = operation_context
    source = new_source(ctx, "siemens-pattern-fixture.pdf")
    _, run_id, units = admitted_page(ctx, source)
    store = InMemoryObjectStorage()
    original = None

    class Provider:
        def execute(self, request):
            nonlocal original
            if request.stage == "EQUIPMENT_RECOGNITION":
                return FakeExtractionProvider("success").execute(request)
            wire = json.loads(request.text)
            payload = {
                key: wire[key] for key in ("version", "stage", "page_context_hash", "upstream_hash")
            }
            payload["attributes"] = [
                dict(
                    origin="EXTRACTED",
                    local_ref=f"item-{i}",
                    equipment_ref="equipment-1",
                    association="ASSERTED",
                    raw_label="Primary connection",
                    raw_value="" if i == 24 else "Wye Ω",
                    raw_unit=None,
                    qualifiers=[],
                    value_form="SINGLE",
                    evidence=[],
                    attribute_key="primary_connection",
                    proposed_unit=None,
                    proposed_value="WYE",
                    alternate_representations=[],
                )
                for i in range(26)
            ]
            payload["raw_unmapped"] = []
            original = (" " + json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
            return AttributeOutput(original, ExecutionUsage(input_tokens=100, output_tokens=50))

    for stage in ("EQUIPMENT_RECOGNITION", "ATTRIBUTE_EXTRACTION"):
        assert execute_unit(
            units[stage],
            ctx["factory"],
            ctx["storage"],
            ctx["settings"],
            lambda _: Provider(),
            audit_storage=store,
        )

    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[1] / "tools/extraction-debugger")
    )
    debugger = importlib.import_module("app")
    role = f"debugger_test_{uuid4().hex}"
    with ctx["factory"].begin() as db:
        engine = db.get_bind()
        db.execute(text(f"CREATE ROLE {role} LOGIN"))
        grant_path = Path(debugger.__file__).with_name("grant-operator.sql")
        quote = engine.dialect.identifier_preparer.quote_identifier
        grants = (
            grant_path.read_text()
            .replace(':"DBNAME"', quote(db.scalar(text("SELECT current_database()"))))
            .replace(':"debugger_operator"', quote(role))
        )
        db.connection().exec_driver_sql(grants)
    reader = create_engine(engine.url.set(username=role, password=None))
    try:
        secret = "test-only-operator-login-secret"
        client = TestClient(
            debugger.create_app(secret, reader, store),
            base_url=debugger.ORIGIN,
            client=("127.0.0.1", 31415),
        )
        headers = {"Origin": debugger.ORIGIN, "X-Debugger-Request": "1"}
        assert (
            client.post("/api/login", headers=headers, json={"secret": secret}).status_code == 204
        )
        attempt = units["ATTRIBUTE_EXTRACTION"]
        reply = client.get(
            "/api/attempts",
            params={
                "identity": str(run_id),
                "validation": "partial",
                "status": "COMPLETED",
                "retention": "true",
                "limit": 1,
            },
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["items"][0]["attempt_id"] == str(attempt)
        assert reply.json()["next_cursor"] is None
        assert (
            client.get(
                "/api/attempts", params={"identity": str(run_id), "cursor": str(attempt)}
            ).json()["items"]
            == []
        )
        assert (
            client.get(
                "/api/attempts", params={"identity": str(attempt), "retention": False}
            ).json()["items"]
            == []
        )
        detail = client.get(f"/api/attempts/{attempt}").json()
        assert detail["attempt"]["published"] == 25
        assert detail["rejections"][0]["index"] == 24
        assert detail["validated"]["attributes"][24]["local_ref"] == "item-25"
        assert detail["candidates"][24]["local_ref"] == "item-25"
        assert detail["candidates"][24]["normalized_value"] == "WYE"
        assert "object_key" not in json.dumps(detail)
        for action in ("original", "export"):
            reply = client.post(f"/api/attempts/{attempt}/{action}", headers=headers)
            assert reply.content == original
        assert (
            reply.headers["Content-Disposition"] == f'attachment; filename="stage2-{attempt}.json"'
        )
        with engine.connect() as db:
            reads = (
                db.execute(
                    text("""
                SELECT operator_name FROM extraction_response_audit_reads WHERE work_unit_id=:id
            """),
                    {"id": attempt},
                )
                .scalars()
                .all()
            )
            assert reads == [role, role]
        from powerforge_extraction.response_audit import ResponseAudit

        with ctx["factory"]() as session:
            key = session.get(ResponseAudit, attempt).object_key
        store.delete(key)
        missing = client.post(f"/api/attempts/{attempt}/original", headers=headers)
        assert missing.status_code == 404 and missing.json()["detail"] == "object_missing"
        from io import BytesIO

        store.put(key, BytesIO(b"X" * len(original)), len(original), "application/json")
        corrupted = client.post(f"/api/attempts/{attempt}/export", headers=headers)
        assert corrupted.status_code == 409 and corrupted.json()["detail"] == "integrity_failed"
        with engine.connect() as db:
            assert (
                db.scalar(
                    text("""
                SELECT count(*) FROM extraction_response_audit_reads WHERE work_unit_id=:id
            """),
                    {"id": attempt},
                )
                == 2
            )
        with reader.begin() as db:
            with pytest.raises(Exception, match="permission denied"):
                db.execute(text("DELETE FROM extraction_candidates WHERE false"))
    finally:
        reader.dispose()
        with engine.begin() as db:
            db.execute(text(f"DROP OWNED BY {role}"))
            db.execute(text(f"DROP ROLE {role}"))
