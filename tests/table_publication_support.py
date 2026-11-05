"""Two manually controlled table units through the existing internal persistence boundary."""

import hashlib
from datetime import UTC, datetime
from io import BytesIO

from extraction_support import inputs, source
from powerforge_api.db import get_session_factory
from powerforge_document_processing.models import DocumentPage, PageArtifact
from powerforge_extraction.contracts import WorkUnitInput
from powerforge_extraction.persistence import ExtractionPersistence
from table_grounding_support import schedule


def plan(ctx, *, reconstruction=None, text=None, image=False, second_page=False):
    reconstruction, generated = schedule() if reconstruction is None else (reconstruction, None)
    src = source(
        ctx, native_text=text if text is not None else generated or "unused native representation"
    )
    factory = get_session_factory()
    with factory.begin() as session:
        artifacts = [src["artifact"]]
        if image:
            from PIL import Image

            buf = BytesIO()
            Image.new("RGB", (20, 20), "white").save(buf, format="PNG")
            data = buf.getvalue()
            key = f"processing/{src['processing']}/table.png"
            ctx["storage"].put(key, BytesIO(data), len(data), "image/png")
            a = PageArtifact(
                document_page_id=src["page"],
                processing_run_id=src["processing"],
                artifact_type="ANALYSIS_IMAGE",
                storage_key=key,
                mime_type="image/png",
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                width_px=20,
                height_px=20,
            )
            session.add(a)
            session.flush()
            artifacts = [*artifacts, a.id] if image == "hybrid" else [a.id]
            src["image"] = a.id
        run_artifacts = list(artifacts)
        if second_page:
            page = DocumentPage(
                document_id=src["document"],
                page_number=2,
                source_width=612,
                source_height=792,
                source_unit="POINTS",
                rotation_degrees=0,
                native_text_char_count=5,
            )
            session.add(page)
            session.flush()
            other = PageArtifact(
                document_page_id=page.id,
                processing_run_id=src["processing"],
                artifact_type="NATIVE_TEXT",
                storage_key=f"processing/{src['processing']}/page2.txt",
                mime_type="text/plain",
                size_bytes=5,
                sha256=hashlib.sha256(b"other").hexdigest(),
            )
            ctx["storage"].put(other.storage_key, BytesIO(b"other"), 5, "text/plain")
            session.add(other)
            session.flush()
            run_artifacts.append(other.id)
            src["other_artifact"] = other.id
        store = ExtractionPersistence(session)
        run = store.create_run(
            inputs(src).model_copy(
                update={
                    "stages": ["TABLE_RECONSTRUCTION", "TABLE_INTERPRETATION"],
                    "input_artifact_ids": run_artifacts,
                    "selected_pages": [1, 2] if second_page else [1],
                }
            )
        )
        run.status, run.started_at = "RUNNING", datetime.now(UTC)
        session.flush()
        units = []
        for stage in run.stages:
            unit = store.create_work_unit(
                run.id,
                WorkUnitInput(
                    unit_key=f"{stage}:page:000001",
                    stage=stage,
                    page_numbers=[1],
                    input_artifact_ids=artifacts,
                ),
            )
            unit.status, unit.started_at = "RUNNING", datetime.now(UTC)
            session.flush()
            units.append(unit.id)
        if second_page:
            other_unit = store.create_work_unit(
                run.id,
                WorkUnitInput(
                    unit_key="TABLE_INTERPRETATION:page:000002",
                    stage="TABLE_INTERPRETATION",
                    page_numbers=[2],
                    input_artifact_ids=[src["other_artifact"]],
                ),
            )
            other_unit.status, other_unit.started_at = "RUNNING", datetime.now(UTC)
            session.flush()
            src["other_unit"] = other_unit.id
        rid = run.id
    return src, rid, *units, factory, reconstruction
