"""Pydantic request/response schemas for projects and revisions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from powerforge_project import ProjectStatus, RevisionStatus


class ProjectCreate(BaseModel):
    project_number: str = Field(min_length=1, max_length=128)
    project_name: str = Field(min_length=1, max_length=512)
    project_address: str | None = None
    project_scope: str | None = None
    client_name: str | None = None
    description: str | None = None
    engineer_names: list[str] = Field(default_factory=list)

    @field_validator("project_number", "project_name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("engineer_names")
    @classmethod
    def clean_engineer_names(cls, value: list[str]) -> list[str]:
        return [name.strip() for name in value if name and name.strip()]


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str | None = Field(default=None, min_length=1, max_length=512)
    project_address: str | None = None
    project_scope: str | None = None
    client_name: str | None = None
    description: str | None = None
    engineer_names: list[str] | None = None

    @field_validator("project_name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("engineer_names")
    @classmethod
    def clean_engineer_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [name.strip() for name in value if name and name.strip()]


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_number: str
    project_name: str
    project_address: str | None
    project_scope: str | None
    client_name: str | None
    description: str | None
    engineer_names: list[str]
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    status_before_archive: ProjectStatus | None = None
    created_by: UUID | None
    active_revision_identifier: str | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]


class RevisionCreate(BaseModel):
    identifier: str = Field(min_length=1, max_length=128)
    description: str | None = None
    activate: bool = False
    based_on_revision_id: UUID | None = Field(
        default=None,
        description=(
            "Revision this one is based on. Omitted: use the project's ACTIVE revision "
            "if one exists, else no base. Explicit null: no base, even if an ACTIVE "
            "revision exists. A UUID: use that revision (must belong to this project)."
        ),
    )
    carry_forward_documents: bool | None = Field(
        default=None,
        description=(
            "Whether to inherit the base revision's INCLUDED documents. Omitted or null: "
            "true when a base is resolved, otherwise false. True without a base is "
            "rejected. False records the base but copies nothing."
        ),
    )

    @field_validator("identifier")
    @classmethod
    def strip_identifier(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class RevisionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    identifier: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def strip_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class RevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    identifier: str
    description: str | None
    status: RevisionStatus
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None
    based_on_revision_id: UUID | None = None
    based_on_identifier: str | None = None
    inherited_document_count: int | None = Field(
        default=None,
        description="Documents inherited at creation. Set only on the create response.",
    )


class RevisionListResponse(BaseModel):
    items: list[RevisionResponse]


class ErrorBody(BaseModel):
    detail: str
    code: str
