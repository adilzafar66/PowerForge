"""Build derived-artifact keys from stable identifiers only."""

from __future__ import annotations

from uuid import UUID

from powerforge_document_model.enums import PageArtifactType
from powerforge_document_model.errors import InvalidArtifactKey

_FILENAMES: dict[PageArtifactType, str] = {
    PageArtifactType.ANALYSIS_IMAGE: "analysis.png",
    PageArtifactType.THUMBNAIL: "thumbnail.webp",
    PageArtifactType.NATIVE_TEXT: "native.txt",
}


def build_artifact_key(
    project_id: UUID,
    document_id: UUID,
    run_id: UUID,
    page_number: int,
    artifact_type: PageArtifactType,
) -> str:
    """Return ``projects/{project}/documents/{document}/processing/{run}/pages/{page}/{file}``."""
    for name, value in (
        ("project_id", project_id),
        ("document_id", document_id),
        ("run_id", run_id),
    ):
        if not isinstance(value, UUID):
            raise TypeError(f"{name} must be a UUID")
    if type(page_number) is not int or page_number < 1:
        raise InvalidArtifactKey("page_number must be an integer >= 1")
    if not isinstance(artifact_type, PageArtifactType):
        raise InvalidArtifactKey("artifact_type is not a PageArtifactType")
    filename = _FILENAMES[artifact_type]
    folder = f"{page_number:04d}"
    return (
        f"projects/{project_id}/documents/{document_id}/processing/"
        f"{run_id}/pages/{folder}/{filename}"
    )
