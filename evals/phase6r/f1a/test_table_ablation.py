from types import SimpleNamespace
from unittest.mock import Mock

from evaluate_sources import settings_for
from evaluate_table_ablation import ARMS, CONTROL, ablation, line_hints, run, word_fingerprints

from extraction_worker.spatial_evaluation import render
from extraction_worker.tesseract import configuration
from powerforge_ai.ocr import OCRIdentity
from powerforge_document_processing import layout_derive, native_spatial
from powerforge_extraction.enrichment_profiles import preparation_profile
from powerforge_extraction.extraction_profile import extraction_profile
from powerforge_provenance.spatial_geometry import NormalizedRegion


def reading(name, x, y="0.1", *, rep="native", issues=()):
    return SimpleNamespace(
        ref=name,
        region=NormalizedRegion(x=x, y=y, width="0.03", height="0.02"),
        preferred=SimpleNamespace(representation_ref=rep),
        issues=issues,
    )


def test_simple_line_hints_do_not_join_wide_gaps_cross_modalities_or_flagged_reads():
    layout = SimpleNamespace(
        readings=(
            reading("a", "0.01"),
            reading("b", "0.05"),
            reading("c", "0.5"),
            reading("d", "0.54", issues=("TRANSCRIPTION_CONFLICT",)),
            reading("e", "0.58", rep="ocr"),
            reading("f", "0.62"),
        ),
        order=(),
    )
    hints = line_hints(layout, 1.3)
    assert [(edge.before, edge.after, edge.basis) for edge in hints] == [
        ("a", "b", "SAME_BASELINE")
    ]


def test_disabled_primitives_and_table_policy_restore_production_functions():
    original = native_spatial.drawing_primitives
    table_function = layout_derive.derive_tables
    original_identity = layout_derive.layout_rules_identity()
    with ablation("positioned_only") as configured:
        assert native_spatial.drawing_primitives(None, 0, 0) == ((), None)
        assert layout_derive.derive_tables(None, None, 0, 0) == ([], [])
        assert configured != original_identity
    assert native_spatial.drawing_primitives is original
    assert layout_derive.derive_tables is table_function
    assert layout_derive.layout_rules_identity() == original_identity


def test_positive_control_keeps_readings_and_evidence_after_removing_confirmed_cells():
    options = configuration("0" * 64)
    provider = SimpleNamespace(
        settings=options,
        identity=OCRIdentity(
            adapter_version="mock-v1",
            engine="tesseract",
            engine_version="5.3.0",
            build_sha256="0" * 64,
            settings_sha256=options.identity_hash,
        ),
        recognize=Mock(side_effect=AssertionError("unexpected OCR")),
    )
    settings = settings_for(provider)
    prep = preparation_profile(settings)
    extraction = extraction_profile(settings)
    data = CONTROL.read_bytes()
    canvas = render(CONTROL, data, 1)
    native = native_spatial.extract_native(data, 1)
    first = None
    from evaluate_table_ablation import evidence_probe

    for arm in ARMS:
        result, streams, layout, source = run(
            CONTROL,
            data,
            canvas,
            1,
            native,
            provider,
            prep,
            extraction,
            arm,
            "default_eligibility",
        )
        assert result["failure"] is None
        assert len(layout.tables) == (1 if arm == "existing_tables" else 0)
        if layout.tables:
            assert sum(len(cell.headers) for cell in layout.tables[0].cells) == 2
        fingerprint = (
            word_fingerprints(streams),
            result["metadata"]["reading_details"],
            evidence_probe(source),
        )
        if first is None:
            first = fingerprint
        assert fingerprint == first
    provider.recognize.assert_not_called()
