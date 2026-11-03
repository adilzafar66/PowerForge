"""HTTP access, exact values, effective outputs and side-effect-free reads."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from documents_support import captured_sql, client, make_project, make_revision
from extraction_support import claim, grounded, inputs, run_and_unit, source, url
from powerforge_api.db import get_session_factory
from powerforge_document_model import RevisionDocumentStatus
from powerforge_document_processing.models import RevisionDocument
from powerforge_extraction.contracts import CandidateInput, WorkUnitOutput
from powerforge_extraction.enums import ExtractionRunStatus, WorkUnitStatus
from powerforge_extraction.persistence import ExtractionPersistence

pytestmark = pytest.mark.integration


def published(ctx):
    src = source(ctx)
    with get_session_factory()() as s:
        run, unit = run_and_unit(s, src)
        candidates = [
            CandidateInput(
                kind="ATTRIBUTE_VALUE",
                mapping_status="MAPPED",
                raw_text="count",
                equipment_type_key="CABLE",
                attribute_key="parallel_run_count",
                value_type="INTEGER",
                integer_value=9007199254740993,
            ),
            CandidateInput(
                kind="ATTRIBUTE_VALUE",
                mapping_status="MAPPED",
                raw_text="750 kVA",
                equipment_type_key="TWO_WINDING_TRANSFORMER",
                attribute_key="rated_apparent_power",
                value_type="NUMBER",
                numeric_value="750.12345678901234567890123456789",
                unit="kVA",
            ),
            CandidateInput(
                kind="ATTRIBUTE_VALUE",
                mapping_status="MAPPED",
                raw_text="No bypass",
                equipment_type_key="UPS",
                attribute_key="static_bypass_available",
                value_type="BOOLEAN",
                boolean_value=False,
            ),
            claim(),
            claim(),
        ]
        output = grounded(src, candidates)
        ExtractionPersistence(s).publish(unit.id, output)
        _, failed = run_and_unit(s, src, key="attributes:failed", run=run)
        failed.status = WorkUnitStatus.FAILED
        s.flush()
        run.status = ExtractionRunStatus.PARTIALLY_COMPLETED
        s.commit()
        return src, run.id, output


def test_read_endpoints_precision_pagination_filters_partial_and_no_writes(ctx):
    src, run, output = published(ctx)
    base = url(ctx, src)
    with captured_sql() as statements:
        summary = client.get(base)
        assert summary.status_code == 200, summary.text
        assert summary.json()["latest_result"]["status"] == "PARTIALLY_COMPLETED"
        history = client.get(base + "/runs?limit=1&offset=0")
        assert history.json()["total"] == 1
        detail = client.get(base + f"/runs/{run}")
        assert detail.json()["coverage"]["complete"] is False
        assert len(detail.json()["coverage"]["effective_work_unit_ids"]) == 1
        assert len(detail.json()["attempts"]) == 2
        response = client.get(base + f"/runs/{run}/candidates")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 5
        values = {v["value_type"]: v for v in body["items"] if v["value_type"]}
        assert values["INTEGER"]["integer_value"] == "9007199254740993"
        assert values["NUMBER"]["numeric_value"] == "750.12345678901234567890123456789"
        assert values["BOOLEAN"]["boolean_value"] is False
        assert all(v["supported"] and len(v["evidence"]) == 1 for v in body["items"])
        first = client.get(base + f"/runs/{run}/candidates?limit=2").json()
        second = client.get(base + f"/runs/{run}/candidates?limit=2&offset=2").json()
        assert len({c["id"] for c in first["items"] + second["items"]}) == 4
        assert (
            client.get(base + f"/runs/{run}/candidates?mapping_status=UNMAPPED").json()["total"]
            == 2
        )
        assert (
            client.get(base + f"/runs/{run}/candidates?attribute_key=parallel_run_count").json()[
                "total"
            ]
            == 1
        )
        assert client.get(base + f"/runs/{run}/tables").json()["items"] == []
        evidence = client.get(base + f"/evidence/{output.evidence[0].id}")
        assert evidence.status_code == 200, evidence.text
        assert evidence.json()["artifact_url"]
        assert evidence.json()["region"] is None
        assert evidence.json()["page_artifact_id"] == str(src["artifact"])
        assert "storage_key" not in evidence.json()
        assert client.get(base + "/runs?limit=0").status_code == 422
    assert all(q.lstrip().upper().startswith("SELECT") for q in statements)


def test_inheritance_superseded_access_and_unrelated_membership_rejected(ctx):
    src, run, _ = published(ctx)
    inherited = make_revision(
        ctx["project_id"],
        "1",
        based_on_revision_id=ctx["revision_id"],
        carry_forward_documents=True,
        activate=True,
    )
    assert inherited.status_code == 201, inherited.text
    with get_session_factory()() as s:
        association = s.scalar(
            select(RevisionDocument).where(
                RevisionDocument.revision_id == UUID(inherited.json()["id"]),
                RevisionDocument.document_id == src["document"],
            )
        )
        inherited_src = {**src, "association": association.id}
    assert client.get(url(ctx, src) + f"/runs/{run}/candidates").status_code == 200
    other_ctx = {**ctx, "revision_id": inherited.json()["id"]}
    assert (
        client.get(url(other_ctx, inherited_src) + f"/runs/{run}/candidates").json()["total"] == 5
    )
    assert client.get(url(other_ctx, src) + f"/runs/{run}").status_code == 404
    unrelated = make_project()
    assert client.get(url({**ctx, "project_id": unrelated}, src)).status_code == 404
    another_src = source(ctx)
    assert client.get(url(ctx, another_src) + f"/runs/{run}").status_code == 404
    assert client.get(url(ctx, another_src) + f"/evidence/{uuid4()}").status_code == 404
    with get_session_factory()() as s:
        association = s.get(RevisionDocument, inherited_src["association"])
        association.status = RevisionDocumentStatus.REMOVED
        from datetime import UTC, datetime

        association.removed_at = datetime.now(UTC)
        s.commit()
    assert client.get(url(other_ctx, inherited_src)).status_code == 404


def test_unsupported_claims_are_explicit_and_not_default_sourced_results(ctx):
    src = source(ctx)
    with get_session_factory()() as s:
        run, unit = run_and_unit(s, src)
        ExtractionPersistence(s).publish(unit.id, WorkUnitOutput(candidates=[claim()]))
        s.commit()
        run_id = run.id
    base = url(ctx, src) + f"/runs/{run_id}/candidates"
    assert client.get(base).json()["total"] == 0
    explicit = client.get(base + "?supported_only=false").json()
    assert explicit["total"] == 1 and explicit["items"][0]["supported"] is False


def test_context_dependent_run_not_reused_in_another_revision(ctx):
    src = source(ctx)
    with get_session_factory()() as s:
        run = ExtractionPersistence(s).create_run(
            inputs(
                src, context_fingerprint="context-v1", context_revision_id=UUID(ctx["revision_id"])
            )
        )
        s.commit()
        run_id = run.id
    new = make_revision(
        ctx["project_id"],
        "other",
        based_on_revision_id=ctx["revision_id"],
        carry_forward_documents=True,
    ).json()
    with get_session_factory()() as s:
        association = s.scalar(
            select(RevisionDocument).where(
                RevisionDocument.revision_id == UUID(new["id"]),
                RevisionDocument.document_id == src["document"],
            )
        )
        other = {**src, "association": association.id}
    assert client.get(url({**ctx, "revision_id": new["id"]}, other) + "/runs").json()["total"] == 0
    assert (
        client.get(url({**ctx, "revision_id": new["id"]}, other) + f"/runs/{run_id}").status_code
        == 404
    )
