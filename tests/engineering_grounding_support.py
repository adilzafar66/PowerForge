"""Pinned in-memory sources and curated observations for grounding behavior tests."""

import hashlib
from dataclasses import replace
from io import BytesIO
from uuid import uuid4

from PIL import Image

from powerforge_document_processing.storage import InMemoryObjectStorage
from powerforge_extraction.engineering_output import MentionContext, RecognitionContext
from powerforge_extraction.grounding import ArtifactSpec, PageSpec, load_page_sources
from powerforge_extraction.observations import (
    AttributeExtractionResponse,
    AttributeObservation,
    EquipmentObservation,
    EquipmentRecognitionResponse,
)


def page(text=None, *, image=False, stage="EQUIPMENT_RECOGNITION"):
    storage, artifacts = InMemoryObjectStorage(), []
    if text is not None:
        data = text.encode()
        storage.put("native", BytesIO(data), len(data), "text/plain")
        artifacts.append(
            ArtifactSpec(
                uuid4(), "native_text", "native", len(data), hashlib.sha256(data).hexdigest()
            )
        )
    if image:
        content = BytesIO()
        Image.new("RGB", (20, 20), "white").save(content, format="PNG")
        data = content.getvalue()
        storage.put("image", BytesIO(data), len(data), "image/png")
        artifacts.append(
            ArtifactSpec(
                uuid4(),
                "analysis_image",
                "image",
                len(data),
                hashlib.sha256(data).hexdigest(),
                20,
                20,
            )
        )
    spec = PageSpec(
        uuid4(),
        uuid4(),
        f"{stage}:page:000001",
        stage,
        uuid4(),
        uuid4(),
        uuid4(),
        1,
        tuple(artifacts),
    )
    return load_page_sources(spec, storage), storage


def attribute_sources(sources):
    return replace(
        sources,
        spec=replace(
            sources.spec,
            unit_id=uuid4(),
            unit_key="ATTRIBUTE_EXTRACTION:page:000001",
            stage="ATTRIBUTE_EXTRACTION",
        ),
    )


def anchor(quote=None, *, visual=False, prefix=None, suffix=None):
    return dict(
        kind="VISUAL_PAGE" if visual else "NATIVE_TEXT",
        source_ref="analysis_image" if visual else "native_text",
        quote=None if visual else quote,
        prefix=prefix,
        suffix=suffix,
    )


def equipment(
    expression,
    *,
    ref="eq1",
    tag=None,
    visual=False,
    quote=None,
    prefix=None,
    suffix=None,
    proposed="TWO_WINDING_TRANSFORMER",
):
    return EquipmentObservation(
        local_ref=ref,
        raw_expression=expression,
        observed_tag=tag,
        observed_name=None,
        proposed_equipment_type=proposed,
        ambiguous=False,
        ambiguity_reason=None,
        anchors=[anchor(quote or expression, visual=visual, prefix=prefix, suffix=suffix)],
    )


def attribute(
    expression="Secondary Voltage: 600 V",
    *,
    ref="a1",
    equipment_ref="eq1",
    visual=False,
    label="Secondary Voltage",
    value="600",
    unit="V",
    key="secondary_voltage",
    proposed="TWO_WINDING_TRANSFORMER",
    quote=None,
    prefix=None,
    suffix=None,
):
    return AttributeObservation(
        local_ref=ref,
        raw_expression=expression,
        equipment_ref=equipment_ref,
        source_label=label,
        raw_value=value,
        raw_unit=unit,
        proposed_equipment_type=proposed,
        proposed_attribute_key=key,
        ambiguous=False,
        ambiguity_reason=None,
        anchors=[anchor(quote or expression, visual=visual, prefix=prefix, suffix=suffix)],
    )


def recognition(*items):
    return EquipmentRecognitionResponse(
        schema_version="equipment-recognition-schema-v1", overflowed=False, equipment=list(items)
    )


def attributes(*items):
    return AttributeExtractionResponse(
        schema_version="attribute-extraction-schema-v1", overflowed=False, attributes=list(items)
    )


def test_context(sources, output):
    """Test-only stand-in for the completed-unit DB loader; production uses that loader."""
    evidence = {item.id: item for item in output.evidence}
    groups = {item.id: item for item in output.source_groups}
    mentions = []
    for candidate in output.candidates:
        group = groups.get(candidate.source_group_id)
        linked = [
            evidence[link.evidence_id]
            for link in output.candidate_evidence
            if link.candidate_id == candidate.id
        ]
        role = "native_text" if linked[0].source_kind == "NATIVE_TEXT" else "analysis_image"
        scope = candidate.diagnostics.get("source_scope")
        mentions.append(
            MentionContext(
                candidate.diagnostics["source_local_ref"],
                candidate.id,
                group.id if group else None,
                linked[0].location.page_artifact_id,
                role,
                candidate.raw_text,
                tuple(scope) if scope else None,
                candidate.observed_tag,
                tuple(item.id for item in linked),
            )
        )
    spec = sources.spec
    return RecognitionContext(
        spec.run_id,
        spec.document_id,
        spec.processing_run_id,
        spec.page_id,
        spec.unit_id,
        tuple(mentions),
    )


test_context.__test__ = False
