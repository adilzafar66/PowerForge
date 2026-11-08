"""Paired 6C conversion on actual Phase 3 output from the same selected originals."""

from pathlib import Path
from tempfile import TemporaryDirectory

from powerforge_extraction.enrichment_prepare import sha
from powerforge_extraction.evaluation import EvalCase, replay, resource_identity
from powerforge_extraction.evaluation_scoring import score_case
from powerforge_extraction.identities import identity_hash

# Separately scripted observations for the two paired pages. Gold claim meaning,
# ownership, and occurrence are supplied by the corpus independently of this replay.
PAIRS = {"prose-native": ("TX-9", "480"), "prose-image": ("TX-12", "600")}


def recording(native, tag, raw):
    def observation(expression, local_ref):
        return {
            "local_ref": local_ref,
            "raw_expression": expression,
            "anchors": [
                {
                    "kind": "NATIVE_TEXT" if native else "VISUAL_PAGE",
                    "source_ref": "native_text" if native else "analysis_image",
                    "quote": expression if native else None,
                    "prefix": None,
                    "suffix": None,
                }
            ],
            "ambiguous": False,
            "ambiguity_reason": None,
            "proposed_equipment_type": None,
        }

    equipment = observation(f"2-Winding Transformer {tag}", "e1")
    equipment.update(observed_tag=tag, observed_name=None)
    attribute = observation(f"Secondary Voltage: {raw} V", "a1")
    attribute.update(
        equipment_ref="e1",
        source_label="Secondary Voltage",
        raw_value=raw,
        raw_unit="V",
        proposed_attribute_key=None,
    )
    return {
        "equipment": {
            "schema_version": "equipment-recognition-schema-v1",
            "overflowed": False,
            "equipment": [equipment],
        },
        "attributes": {
            "schema_version": "attribute-extraction-schema-v1",
            "overflowed": False,
            "attributes": [attribute],
        },
    }


def prose_pair(case, page, enhanced):
    native = case.baseline == "prose-native"
    tag, raw = PAIRS[case.baseline]
    observations = recording(native, tag, raw)
    answer = {
        "source_sha256": case.sha256,
        "page": case.page,
        "legacy_profile_source": "NATIVE_TEXT" if native else "VISUAL_PAGE",
        "legacy_resources": resource_identity(),
        "legacy_observations_sha256": identity_hash(observations),
        "enhanced": enhanced["mock_conversion"]["prose"]["metrics"],
        "policy": "Same originals and printed claims. Legacy visual evidence is page-level.",
    }
    if page is None or (native and page.native_text is None):
        return {
            **answer,
            "legacy_failure": "MISSING_RENDERED_SOURCE",
            "gold_claims": len(case.claims),
        }

    data = page.native_text.encode() if native else page.analysis_png
    role = "native_text" if native else "analysis_image"
    words = {word.id: word.text for word in case.words}
    lines = {line.id: " ".join(words[id_] for id_ in line.words) for line in case.lines}
    expected = []
    for claim in case.claims:
        expression = lines[claim.line]
        span = None
        if native and page.native_text.count(expression) == 1:
            start = page.native_text.index(expression)
            span = [start, start + len(expression)]
        expected.append(
            {
                "id": claim.id,
                "kind": claim.kind,
                "expression": expression,
                "role": role,
                "span": span,
                "precision": ["TEXT_OFFSETS"] if native else ["VISUAL_PAGE"],
                "status": claim.status,
                "equipment_type": claim.equipment_type,
                "tag": claim.tag,
                "attribute_key": claim.attribute,
                "value_type": claim.value_type,
                "value": claim.value,
                "unit": claim.unit,
                "equipment": claim.owner,
                "raw_value": raw if claim.kind == "ATTRIBUTE_VALUE" else None,
                "raw_unit": "V" if claim.kind == "ATTRIBUTE_VALUE" else None,
            }
        )

    basename = "source.txt" if native else "source.png"
    gold = EvalCase.model_validate(
        {
            "id": case.id,
            "family": "paired-spatial-evaluation",
            "note": case.note,
            "sources": [
                {
                    "role": role,
                    "path": basename,
                    "sha256": sha(data),
                    "size_bytes": len(data),
                    "width": None if native else page.width_px,
                    "height": None if native else page.height_px,
                }
            ],
            "expected": expected,
        }
    )
    with TemporaryDirectory(prefix="powerforge-paired-6c-") as folder:
        root = Path(folder)
        (root / basename).write_bytes(data)
        sources, outputs, failures = replay(gold, root, observations)
    result = score_case(gold, sources, outputs)
    return {**answer, "legacy": result["counts"], "legacy_stage_failures": failures}
