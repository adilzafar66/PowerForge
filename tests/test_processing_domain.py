"""Pure processing vocabulary: enums, profile hash, artifact keys (PR-02)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from powerforge_document_model import (
    DEFAULT_PROFILE,
    PROCESSOR_VERSION,
    PROFILE_VERSION,
    InvalidArtifactKey,
    NormalizedBox,
    PageArtifactType,
    ProcessingErrorCode,
    ProcessingProfile,
    ProcessingRunStatus,
    SourceUnit,
    build_artifact_key,
    hash_material_fields,
)

RUN_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED")
ARTIFACT_TYPES = ("ANALYSIS_IMAGE", "THUMBNAIL", "NATIVE_TEXT")
SOURCE_UNITS = ("POINTS", "PIXELS")
ERROR_CODES = (
    "CORRUPT_PDF",
    "PASSWORD_PROTECTED_PDF",
    "IMAGE_DECODE_FAILED",
    "UNSUPPORTED_SOURCE",
    "PAGE_RENDER_FAILED",
    "STORAGE_READ_FAILED",
    "STORAGE_WRITE_FAILED",
    "RESOURCE_LIMIT_EXCEEDED",
    "PROCESSING_TIMEOUT",
    "UNKNOWN_PROCESSING_ERROR",
)
ARTIFACT_FILES = {
    PageArtifactType.ANALYSIS_IMAGE: "analysis.png",
    PageArtifactType.THUMBNAIL: "thumbnail.webp",
    PageArtifactType.NATIVE_TEXT: "native.txt",
}


@pytest.mark.parametrize(
    ("enum_type", "expected"),
    [
        (ProcessingRunStatus, RUN_STATUSES),
        (PageArtifactType, ARTIFACT_TYPES),
        (SourceUnit, SOURCE_UNITS),
        (ProcessingErrorCode, ERROR_CODES),
    ],
)
def test_enum_values_and_declaration_order(enum_type: type, expected: tuple[str, ...]) -> None:
    assert [member.value for member in enum_type] == list(expected)
    for name in expected:
        assert enum_type[name].value == name


def test_default_profile_hash_is_stable_and_ignores_versions() -> None:
    assert DEFAULT_PROFILE.processor_version == PROCESSOR_VERSION == "1"
    assert DEFAULT_PROFILE.profile_version == PROFILE_VERSION == "engineering-default-v1"
    assert DEFAULT_PROFILE.profile_hash == ProcessingProfile().profile_hash

    renamed = ProcessingProfile(processor_version="9", profile_version="other-label")
    assert renamed.profile_hash == DEFAULT_PROFILE.profile_hash
    assert "processor_version" not in DEFAULT_PROFILE.material_fields()
    assert "profile_version" not in DEFAULT_PROFILE.material_fields()


def test_profile_hash_changes_when_a_material_field_changes() -> None:
    baseline = DEFAULT_PROFILE.profile_hash
    assert ProcessingProfile(target_dpi=300).profile_hash != baseline
    assert ProcessingProfile(max_total_pixels=1_000_000).profile_hash != baseline
    assert ProcessingProfile(thumbnail_long_edge_px=400).profile_hash != baseline


def test_profile_hash_ignores_dict_insertion_order() -> None:
    fields = DEFAULT_PROFILE.material_fields()
    reversed_fields = {key: fields[key] for key in reversed(fields)}
    assert list(reversed_fields) != list(fields)
    assert hash_material_fields(reversed_fields) == hash_material_fields(fields)
    assert hash_material_fields(fields) == DEFAULT_PROFILE.profile_hash


def test_artifact_key_uses_stable_ids_and_zero_padded_pages() -> None:
    project_id = uuid4()
    document_id = uuid4()
    run_id = uuid4()
    key = build_artifact_key(
        project_id, document_id, run_id, 1, PageArtifactType.ANALYSIS_IMAGE
    )
    assert key == (
        f"projects/{project_id}/documents/{document_id}/processing/"
        f"{run_id}/pages/0001/analysis.png"
    )
    page_12 = build_artifact_key(
        project_id, document_id, run_id, 12, PageArtifactType.THUMBNAIL
    )
    assert page_12.endswith("/pages/0012/thumbnail.webp")
    text = build_artifact_key(
        project_id, document_id, run_id, 3, PageArtifactType.NATIVE_TEXT
    )
    assert text.endswith("/pages/0003/native.txt")
    for artifact_type, filename in ARTIFACT_FILES.items():
        built = build_artifact_key(project_id, document_id, run_id, 2, artifact_type)
        assert built.endswith(f"/pages/0002/{filename}")


def test_artifact_key_rejects_bad_page_type_and_uuid() -> None:
    project_id = uuid4()
    document_id = uuid4()
    run_id = uuid4()
    with pytest.raises(InvalidArtifactKey):
        build_artifact_key(project_id, document_id, run_id, 0, PageArtifactType.ANALYSIS_IMAGE)
    with pytest.raises(InvalidArtifactKey):
        build_artifact_key(project_id, document_id, run_id, 1, "NOPE")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_artifact_key("not-a-uuid", document_id, run_id, 1, PageArtifactType.ANALYSIS_IMAGE)  # type: ignore[arg-type]


def test_artifact_key_does_not_embed_filename_revision_or_classification() -> None:
    project_id = uuid4()
    document_id = uuid4()
    run_id = uuid4()
    key = build_artifact_key(
        project_id, document_id, run_id, 4, PageArtifactType.ANALYSIS_IMAGE
    )
    assert "SLD.pdf" not in key
    assert "SINGLE_LINE_DIAGRAM" not in key
    assert "revision" not in key


def test_normalized_box_accepts_unit_interval_and_rejects_outside() -> None:
    box = NormalizedBox(x=0.312, y=0.164, width=0.121, height=0.043)
    assert box.x == 0.312
    NormalizedBox(x=0.0, y=0.0, width=1.0, height=1.0)
    with pytest.raises(ValueError):
        NormalizedBox(x=-0.01, y=0.0, width=0.1, height=0.1)
    with pytest.raises(ValueError):
        NormalizedBox(x=0.0, y=1.1, width=0.1, height=0.1)
