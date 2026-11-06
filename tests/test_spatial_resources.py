"""Pure imports, packaged new identities and source-preserving compatibility checks."""

import json
import subprocess
import sys

import pytest

from powerforge_ai.ocr import ocr_contract_identity
from powerforge_provenance.spatial_base import POLICY, TextSpan, canonical_json, identity_hash
from powerforge_provenance.spatial_identity import spatial_contract_identity
from powerforge_provenance.spatial_layout import (
    SourceBinding,
    SourceSupport,
    SpatialPage,
    SpatialRegion,
    resolve_region_support,
)
from powerforge_provenance.spatial_offsets import NativeEmissionTrace, NativeOriginDataset
from powerforge_provenance.spatial_sources import (
    PositionedText,
    PositionedToken,
    PreparedPage,
    checked_positioned_text,
)
from spatial_support import ROOT, sha, snapshot

FIXTURES = ROOT / "tests/fixtures/enrichment"
CASES = json.loads((FIXTURES / "spatial_sources_v1.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_authored_native_ocr_unicode_sparse_and_unavailable_fixture_contracts(case):
    prepared = PreparedPage.model_validate_json(json.dumps(case["prepared"]))
    body = PositionedText.model_validate_json(json.dumps(case["positioned"]))
    encoded = case["text"].encode()
    checked_positioned_text(body, encoded)
    assert PreparedPage.model_validate_json(prepared.model_dump_json()) == prepared
    expected = case["expected_support"]
    if expected is not None:
        alias = prepared.representations[0].ref
        region = SpatialRegion(
            ref="fixture-cell",
            kind="CELL",
            region=None,
            support=(SourceSupport(representation_ref=alias, kind="TOKEN", ref=expected["ref"]),),
        )
        answer = resolve_region_support(
            prepared, region, {alias: canonical_json(case["positioned"]).encode()}, {alias: encoded}
        )
        assert answer.basis == expected["basis"]
        assert (answer.region is None) == (expected["region"] is None)
        if answer.region is not None:
            from powerforge_provenance.spatial_geometry import NormalizedRegion

            assert answer.region == NormalizedRegion.model_validate_json(
                json.dumps(expected["region"])
            )
        assert answer.structure_basis == "UNRESOLVED"
    if case["id"] == "native_pdf_reference":
        assert prepared.original.sha256 == sha(
            (ROOT / "evals/tables/v1/sources/positioned_schedule.pdf").read_bytes()
        )
        assert encoded == (ROOT / "evals/tables/v1/sources/pdf_native_unresolved.txt").read_bytes()


def test_new_resource_and_schema_identities_and_accepted_source_bytes_are_pinned():
    fixture = json.loads((FIXTURES / "spatial_v1_identity.json").read_text())
    assert fixture["spatial"] == spatial_contract_identity()
    assert fixture["ocr"] == ocr_contract_identity()
    assert fixture["fixture_sha256"] == sha((FIXTURES / "spatial_sources_v1.json").read_bytes())
    for cls in (
        PositionedText,
        SpatialPage,
        SourceBinding,
        NativeEmissionTrace,
        NativeOriginDataset,
    ):
        assert fixture["schemas"][cls.__name__] == identity_hash(cls.model_json_schema())
    for relative, digest in fixture["frozen_legacy_files"].items():
        assert sha((ROOT / relative).read_bytes()) == digest, relative


def large_body(count, *, long_labels=False):
    source = snapshot(missing_geometry=True)
    data = "\n".join("x" for _ in range(count)).encode()
    text = source.body.text_artifact.model_copy(
        update={"sha256": sha(data), "size_bytes": len(data)}
    )
    tokens = tuple(
        PositionedToken(
            ref=f"w{i}",
            raw_text="x",
            span=TextSpan(start=2 * i, end=2 * i + 1),
            engine_order=i,
            source_box=None,
            geometry_unavailable_reason="😀" * 200 if long_labels else "UNAVAILABLE",
        )
        for i in range(count)
    )
    return source.body.model_copy(
        update={"text_artifact": text, "tokens": tokens, "lines": (), "blocks": ()}
    ), data


def test_maximum_token_shape_fits_its_measured_canonical_bound_without_silent_truncation():
    body, data = large_body(POLICY["max_tokens"])
    checked, _ = checked_positioned_text(body, data)
    assert len(checked.tokens) == 20_000
    assert (
        len(canonical_json(checked.model_dump(mode="json")).encode()) < POLICY["max_manifest_bytes"]
    )
    fixture = json.loads((FIXTURES / "spatial_v1_identity.json").read_text())
    assert (
        len(canonical_json(checked.model_dump(mode="json")).encode())
        == fixture["measurements"]["max_minimal_positioned_bytes"]
    )


def test_utf8_byte_capacity_is_independent_of_legal_token_and_character_counts():
    body, data = large_body(6000, long_labels=True)
    assert len(body.tokens) < POLICY["max_tokens"] and len(data) < POLICY["max_text_characters"]
    with pytest.raises(ValueError, match="UTF-8"):
        checked_positioned_text(body, data)


def test_new_contracts_import_without_processing_orm_registry_or_provider_dependencies():
    script = """
import builtins
original=builtins.__import__
blocked={'sqlalchemy','openai','celery','boto3','PIL','pymupdf','fitz','fastapi',
         'powerforge_extraction','powerforge_engineering_model','powerforge_document_processing'}
def guarded(name,*args,**kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('Infrastructure imported by pure contract: '+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from powerforge_provenance.spatial_identity import spatial_contract_identity
from powerforge_provenance.spatial_sources import PositionedText
from powerforge_provenance.spatial_layout import SourceBinding
from powerforge_provenance.spatial_offsets import NativeEmissionTrace
from powerforge_ai.ocr import ocr_contract_identity,PositionedOCRProvider
print(spatial_contract_identity()['version'],ocr_contract_identity()['version'])
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "spatial-source-contracts-v1 positioned-ocr-provider-v1"
