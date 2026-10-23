"""Pure ORM/package checks, independent of a database."""

import ast
import warnings
from pathlib import Path

from sqlalchemy import Text
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import configure_mappers

from powerforge_document_processing import models as documents
from powerforge_engineering_model import (
    AttributeValueType,
    InformationState,
    LifecycleStatus,
    ValueOrigin,
    VerificationState,
)
from powerforge_persistence import Base, Project, ProjectRevision, engineering
from powerforge_persistence.engineering import Equipment, EquipmentAttribute, EquipmentLineage


def test_neutral_base_and_compatibility_class_identity() -> None:
    assert documents.Base is Base
    assert documents.Project is Project
    assert documents.ProjectRevision is ProjectRevision
    assert Project.__module__ == "powerforge_persistence.projects"
    assert documents.Document.metadata is Equipment.metadata is Base.metadata
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        configure_mappers()


def test_persistence_states_match_domain_and_use_migration_owned_enums() -> None:
    for mapping, domain in [
        (engineering.lifecycle_status_enum, LifecycleStatus),
        (engineering.value_origin_enum, ValueOrigin),
        (engineering.information_state_enum, InformationState),
        (engineering.verification_state_enum, VerificationState),
        (engineering.attribute_value_type_enum, AttributeValueType),
    ]:
        assert mapping.enums == [v.value for v in domain]
        assert not mapping.create_type
    assert {v.value for v in LifecycleStatus} == {"ACTIVE", "REMOVED"}
    assert {v.value for v in ValueOrigin} == {"MANUAL", "AI_EXTRACTION", "INFERRED", "IMPORTED"}
    assert type(Equipment.__table__.c.equipment_type.type) is Text
    assert type(EquipmentAttribute.__table__.c.attribute_key.type) is Text
    assert type(EquipmentAttribute.__table__.c.unit.type) is Text
    assert set(EquipmentLineage.__table__.columns.keys()) == {
        "id",
        "project_id",
        "created_at",
        "created_by",
    }
    assert not {"required", "critical", "confidence", "parent_equipment_id"} & set(
        Equipment.__table__.columns.keys()
    )
    assert not {"required", "critical", "document_id"} & set(
        EquipmentAttribute.__table__.columns.keys()
    )


def test_persistence_has_no_document_or_api_dependency() -> None:
    root = Path(__file__).resolve().parents[1] / "packages/persistence/src"
    for file in root.rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            modules = (
                [n.name for n in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            )
            for module in modules:
                assert not module.startswith(
                    ("powerforge_document", "powerforge_api", "fastapi", "celery")
                )


def test_neutral_guards_reexport_same_lock_functions() -> None:
    from powerforge_api.services import revision_documents, revision_writes

    assert revision_documents.lock_revision is revision_writes.lock_revision
    assert revision_documents.lock_project_shared is revision_writes.lock_project_shared
    assert revision_documents.assert_project_modifiable is revision_writes.assert_project_modifiable
