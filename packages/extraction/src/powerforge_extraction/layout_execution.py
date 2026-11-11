"""Source preparation reuse and local layout on the shared leased execution lifecycle."""

import time
from dataclasses import replace
from io import BytesIO
from uuid import UUID, uuid4

from powerforge_ai.extraction import ErrorCode
from powerforge_document_processing.layout_derive import admit_layout, derive_layout
from powerforge_document_processing.layout_limits import LayoutBound
from powerforge_document_processing.storage.base import StorageError, TransientStorageError
from powerforge_extraction.controls import RunExecution
from powerforge_extraction.enrichment_execution import execute_preparation
from powerforge_extraction.enrichment_profiles import PURPOSE
from powerforge_extraction.errors import LeaseLost
from powerforge_extraction.execution import heartbeats
from powerforge_extraction.layout_profiles import require_layout
from powerforge_extraction.layout_service import (
    publish_layout,
    publish_receipt,
    spatial_key,
    validate_layout_plan,
)
from powerforge_extraction.layout_sources import (
    load_prepared,
    preparation_for_layout,
    successful_prepared,
)
from powerforge_extraction.models import ExtractionRun, ExtractionWorkUnit
from powerforge_extraction.orchestration import ExtractionCoordinator
from powerforge_extraction.profiles import read_profile
from powerforge_provenance.spatial_base import canonical_json


def preparation_claim(claim):
    require_layout(claim.profile)
    if claim.unit_key != f"SOURCE_PREPARE:page:{claim.page_number:06d}":
        raise ValueError("Only the preparation stage may invoke the preparation adapter")
    return replace(claim, profile=claim.profile.preparation)


def execute_enrichment(unit_id, factory, storage, settings, provider_factory):
    with factory() as session:
        unit = session.get(ExtractionWorkUnit, unit_id)
        if unit is None or session.get(ExtractionRun, unit.run_id).execution_purpose != PURPOSE:
            return False
        profile = read_profile(session.get(RunExecution, unit.run_id).configuration)
        if profile.version != "source-layout-profile-v1":
            mode = "PREPARE"
        else:
            validate_layout_plan(unit, profile)
            mode = (
                "LAYOUT"
                if unit.stage == "SPATIAL_LAYOUT"
                else "REUSE"
                if unit.execution_metadata.get("reuse_result_id")
                else "PREPARE"
            )
    if mode == "PREPARE":
        return execute_preparation(unit_id, factory, storage, settings, provider_factory)
    with factory.begin() as session:
        claim = ExtractionCoordinator(session, settings).claim(unit_id, purpose=PURPOSE)
    if claim is None:
        return False
    try:
        with heartbeats(factory, claim, settings):
            require_layout(claim.profile)
            started = time.monotonic()
            cpu = time.process_time()
            with factory() as session:
                unit = session.get(ExtractionWorkUnit, unit_id)
                validate_layout_plan(unit, claim.profile)
                snapshot = (
                    successful_prepared(session, UUID(unit.execution_metadata["reuse_result_id"]))
                    if mode == "REUSE"
                    else preparation_for_layout(session, unit)
                )
                if (
                    mode == "REUSE"
                    and snapshot.manifest.identity_hash
                    != unit.execution_metadata["reuse_manifest_hash"]
                ):
                    raise ValueError("Pinned preparation receipt differs from original manifest")
            geometry, text, read_bytes = load_prepared(snapshot, storage)
            if mode == "REUSE":
                with factory.begin() as session:
                    publish_receipt(session, settings, claim, snapshot)
            else:
                layout = derive_layout(
                    snapshot.manifest,
                    geometry,
                    text,
                    uuid4(),
                    claim.run_id,
                    claim.unit_id,
                )
                admit_layout(snapshot.manifest, geometry, text, layout)
                data = canonical_json(layout.model_dump(mode="json")).encode()
                storage.put(
                    spatial_key(layout.owner.document_id, layout.id),
                    BytesIO(data),
                    len(data),
                    "application/json",
                )
                usage = dict(
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    python_cpu_ms=int((time.process_time() - cpu) * 1000),
                    bytes_read=read_bytes,
                    bytes_written=len(data),
                    ocr_invocations=0,
                    operating_cost=None,
                )
                with factory.begin() as session:
                    publish_layout(
                        session, settings, claim, snapshot, geometry, text, layout, usage
                    )
    except LeaseLost:
        return False
    except Exception as exc:
        code = (
            ErrorCode.SOURCE_UNAVAILABLE.value
            if isinstance(exc, TransientStorageError)
            else ErrorCode.TIMEOUT.value
            if type(exc).__name__ == "SoftTimeLimitExceeded"
            else exc.reason
            if isinstance(exc, LayoutBound)
            else ErrorCode.INPUT.value
            if isinstance(exc, (ValueError, OSError, StorageError, UnicodeError))
            else ErrorCode.INTERNAL.value
        )
        try:
            with factory.begin() as session:
                coordinator = ExtractionCoordinator(session, settings)
                run, unit, _ = coordinator._authorized(claim.unit_id, claim.token)
                coordinator._settle_failure(run, unit, claim.profile, code)
        except LeaseLost:
            return False
        except Exception:
            raise RuntimeError(
                "Spatial execution state unavailable; lease recovery required"
            ) from None
    return True
