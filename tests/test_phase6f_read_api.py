"""Phase 6F read and recovery contracts over real PostgreSQL, without provider calls."""

import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from documents_support import captured_sql, client, make_project, make_revision
from extraction_support import claim, grounded, inputs, run_and_unit, source, url
from powerforge_api.db import get_session_factory
from powerforge_document_model import DEFAULT_PROFILE
from powerforge_document_processing.models import DocumentProcessingRun, PageArtifact
from powerforge_extraction.contracts import SourceGroupInput
from powerforge_extraction.controls import RunExecution, UnitExecution
from powerforge_extraction.persistence import ExtractionPersistence
from powerforge_extraction.production_profiles import ENGINEERING_OPENAI_PROFILE, production_profile
from powerforge_extraction.table_profiles import TABLE_OPENAI_PROFILE, table_profile
from powerforge_shared.config import get_settings

pytestmark = pytest.mark.integration


def processed_source(ctx):
    src = source(ctx)
    with get_session_factory()() as session:
        processing = session.get(DocumentProcessingRun, src["processing"])
        processing.processor_version = DEFAULT_PROFILE.processor_version
        processing.profile_version = DEFAULT_PROFILE.profile_version
        processing.profile_hash = DEFAULT_PROFILE.profile_hash
        image = b"test image descriptor"
        artifact = PageArtifact(
            document_page_id=src["page"],
            processing_run_id=src["processing"],
            artifact_type="ANALYSIS_IMAGE",
            storage_key=f"processing/{src['processing']}/image.png",
            mime_type="image/png",
            size_bytes=len(image),
            sha256=hashlib.sha256(image).hexdigest(),
            width_px=800,
            height_px=600,
        )
        ctx["storage"].put(artifact.storage_key, BytesIO(image), len(image), "image/png")
        session.add(artifact)
        session.commit()
    return src


def create_run(session, src, profile):
    store = ExtractionPersistence(session)
    run = store.create_run(
        inputs(src).model_copy(
            update={
                "provider": profile.provider,
                "model": profile.model,
                "profile_hash": profile.identity_hash,
                "profile_version": profile.version,
                "prompt_hash": profile.prompt_hash,
                "prompt_version": profile.prompt_version,
            }
        )
    )
    session.add(RunExecution(run_id=run.id, configuration=profile.model_dump(mode="json")))
    session.flush()
    return run


def publish_groups(ctx, src, profile, count):
    with get_session_factory()() as session:
        run = create_run(session, src, profile)
        _, unit = run_and_unit(session, src, run=run)
        now = datetime.now(UTC)
        token = uuid4()
        unit.lease_expires_at = now + timedelta(minutes=1)
        session.add(
            UnitExecution(
                work_unit_id=unit.id,
                run_id=run.id,
                unit_key=unit.unit_key,
                token=token,
                available_at=now,
                dispatch_after=now,
                hard_deadline_at=unit.lease_expires_at,
            )
        )
        session.flush()
        session.execute(
            select(func.set_config("powerforge.extraction_lease_token", str(token), True))
        )
        groups = [
            SourceGroupInput(
                local_key=f"group-{index}",
                tag_text=f"TX-{index:02d}",
                equipment_type_hint="TWO_WINDING_TRANSFORMER",
            )
            for index in range(count)
        ]
        candidates = [claim(source_group_id=group.id, raw_value="750") for group in groups]
        candidates.extend([claim(raw_value="750"), claim(source_group_id=groups[0].id)])
        output = grounded(src, candidates).model_copy(update={"source_groups": groups})
        ExtractionPersistence(session, ctx["storage"]).publish(unit.id, output)
        run.status = "COMPLETED"
        session.commit()
        return run.id, groups, output.evidence[0].id


def test_register_keeps_family_attempts_effective_results_and_membership_separate(ctx):
    src = processed_source(ctx)
    foreign_project = make_project()
    foreign_revision = make_revision(foreign_project, "0", activate=True).json()["id"]
    foreign = source({**ctx, "project_id": foreign_project, "revision_id": foreign_revision})
    settings = get_settings()
    engineering = production_profile(ENGINEERING_OPENAI_PROFILE, settings)
    tables = table_profile(TABLE_OPENAI_PROFILE, settings)
    engineering_id, _, _ = publish_groups(ctx, src, engineering, 1)
    tables_id, _, _ = publish_groups(ctx, src, tables, 1)
    with get_session_factory()() as session:
        newer = create_run(session, src, engineering)
        newer_id = newer.id
        session.commit()

    base = f"/api/projects/{ctx['project_id']}/revisions/{ctx['revision_id']}/extraction/status"
    params = [
        ("revision_document_ids", str(src["association"])),
        ("revision_document_ids", str(foreign["association"])),
    ]
    with captured_sql() as sql:
        result = client.get(base, params=params)
    assert result.status_code == 200, result.text
    assert len([stmt for stmt in sql if stmt.lstrip().upper().startswith("SELECT")]) <= 3
    [item] = result.json()["items"]
    assert item["ineligible_reason"] is None
    assert item["engineering"]["latest_attempt"]["id"] == str(newer_id)
    assert item["engineering"]["effective_result"]["id"] == str(engineering_id)
    assert item["tables"]["effective_result"]["id"] == str(tables_id)
    assert (
        client.get(base, params=[("revision_document_ids", str(uuid4()))] * 101).status_code == 422
    )

    make_revision(ctx["project_id"], "1", activate=True)
    result = client.get(base, params=params)
    assert result.json()["items"][0]["ineligible_reason"] == "READ_ONLY"
    history = url(ctx, src) + f"/runs/{newer_id}"
    assert client.get(history, params={"family": "engineering"}).json()["can_cancel"] is False
    cancel = client.post(history + "/cancel", params={"family": "engineering"})
    assert cancel.status_code == 409, cancel.text
    assert client.get(history).json()["run"]["status"] == "PENDING"


def test_group_pages_search_ungrouped_and_exact_evidence_stay_run_scoped(ctx):
    src = processed_source(ctx)
    settings = get_settings()
    engineering, groups, evidence = publish_groups(
        ctx, src, production_profile(ENGINEERING_OPENAI_PROFILE, settings), 52
    )
    tables, _, _ = publish_groups(ctx, src, table_profile(TABLE_OPENAI_PROFILE, settings), 2)
    base = url(ctx, src)
    pair = {"engineering_run_id": str(engineering), "tables_run_id": str(tables)}
    first = client.get(base + "/groups", params={**pair, "limit": 25})
    assert first.status_code == 200, first.text
    assert first.json()["total"] == 56
    second = client.get(base + "/groups", params={**pair, "limit": 25, "offset": 25})
    assert len(second.json()["items"]) == 25

    def keys(page):
        return {(item["run_id"], item["source_group_id"]) for item in page.json()["items"]}

    assert keys(first).isdisjoint(keys(second))

    filters = {"search": "TX-00", "page": 1, "mapping_status": "UNMAPPED"}
    filtered = client.get(base + "/groups", params={**pair, **filters})
    assert filtered.status_code == 200, filtered.text
    assert {item["run_id"] for item in filtered.json()["items"]} == {str(engineering), str(tables)}
    assert {item["candidate_count"] for item in filtered.json()["items"]} == {2}
    for item in filtered.json()["items"]:
        candidates = client.get(
            base + f"/runs/{item['run_id']}/candidates",
            params={**filters, "source_group_id": item["source_group_id"]},
        )
        assert candidates.status_code == 200, candidates.text
        assert candidates.json()["total"] == item["candidate_count"]
    assert client.get(base + "/groups", params={**pair, "page": 2}).json()["total"] == 0
    assert (
        client.get(base + "/groups", params={**pair, "engineering_run_id": str(tables)}).status_code
        == 404
    )
    other = processed_source(ctx)
    assert client.get(url(ctx, other) + "/groups", params=pair).status_code == 404

    candidates_url = base + f"/runs/{engineering}/candidates"
    grouped = client.get(candidates_url, params={"source_group_id": str(groups[0].id), "page": 1})
    assert grouped.status_code == 200, grouped.text
    assert len({item["id"] for item in grouped.json()["items"]}) == 2
    assert grouped.json()["items"][0]["evidence"][0]["evidence"]["source_page_number"] == 1
    ungrouped = client.get(candidates_url, params={"ungrouped": True})
    assert ungrouped.json()["total"] == 1

    detail = client.get(base + f"/evidence/{evidence}", params={"include_source_image": True})
    assert detail.status_code == 200, detail.text
    assert detail.json()["processing_run_id"] == str(src["processing"])
    assert detail.json()["source_image_url"]
    assert detail.json()["source_image_width_px"] == 800
    assert detail.json()["region"] is None
