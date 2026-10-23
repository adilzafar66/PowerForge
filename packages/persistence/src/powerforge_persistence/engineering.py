"""Revision-scoped canonical equipment storage. Registry semantics live in the domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from powerforge_engineering_model import (
    AttributeValueType,
    InformationState,
    LifecycleStatus,
    ValueOrigin,
    VerificationState,
)
from powerforge_persistence import Base

lifecycle_status_enum = ENUM(
    LifecycleStatus,
    name="model_lifecycle_status",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
value_origin_enum = ENUM(
    ValueOrigin,
    name="model_value_origin",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
information_state_enum = ENUM(
    InformationState,
    name="model_information_state",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
verification_state_enum = ENUM(
    VerificationState,
    name="model_verification_state",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)
attribute_value_type_enum = ENUM(
    AttributeValueType,
    name="model_attribute_value_type",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)

TYPED_VALUE_CHECK = """
(information_state <> 'PRESENT'
    AND num_nonnulls(numeric_value, integer_value, text_value, boolean_value) = 0)
OR (information_state = 'PRESENT'
    AND num_nonnulls(numeric_value, integer_value, text_value, boolean_value) = 1
    AND ((value_type = 'NUMBER' AND numeric_value IS NOT NULL)
      OR (value_type = 'INTEGER' AND integer_value IS NOT NULL)
      OR (value_type IN ('TEXT', 'ENUM') AND text_value IS NOT NULL)
      OR (value_type = 'BOOLEAN' AND boolean_value IS NOT NULL)))
"""


class EquipmentLineage(Base):
    __tablename__ = "equipment_lineages"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_equipment_lineages_project_id_id"),
        Index("ix_equipment_lineages_project_id", "project_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", name="fk_equipment_lineages_project_id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("revision_id", "lineage_id", name="uq_equipment_revision_lineage"),
        UniqueConstraint("project_id", "id", name="uq_equipment_project_id_id"),
        UniqueConstraint(
            "project_id", "revision_id", "id", name="uq_equipment_project_revision_id"
        ),
        ForeignKeyConstraint(
            ["project_id", "revision_id"],
            ["project_revisions.project_id", "project_revisions.id"],
            name="fk_equipment_revision",
        ),
        ForeignKeyConstraint(
            ["project_id", "lineage_id"],
            ["equipment_lineages.project_id", "equipment_lineages.id"],
            name="fk_equipment_lineage",
        ),
        ForeignKeyConstraint(
            ["project_id", "inherited_from_equipment_id"],
            ["equipment.project_id", "equipment.id"],
            name="fk_equipment_inherited_from",
        ),
        CheckConstraint(
            "inherited_from_equipment_id IS NULL OR inherited_from_equipment_id <> id",
            name="ck_equipment_inherited_not_self",
        ),
        CheckConstraint(
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL) OR "
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL AND removed_by IS NULL)",
            name="ck_equipment_lifecycle_removed_at",
        ),
        Index("ix_equipment_revision_lifecycle", "revision_id", "lifecycle_status"),
        Index("ix_equipment_project_id", "project_id"),
        Index("ix_equipment_lineage_id", "lineage_id"),
        Index("ix_equipment_revision_tag", "revision_id", "tag"),
        Index("ix_equipment_inherited_from", "inherited_from_equipment_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lineage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    equipment_type: Mapped[str] = mapped_column(Text, nullable=False)
    tag: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        lifecycle_status_enum, server_default=text("'ACTIVE'::model_lifecycle_status")
    )
    origin: Mapped[ValueOrigin] = mapped_column(
        value_origin_enum, server_default=text("'MANUAL'::model_value_origin")
    )
    verification_state: Mapped[VerificationState] = mapped_column(
        verification_state_enum,
        server_default=text("'ENGINEER_REVIEWED'::model_verification_state"),
    )
    inherited_from_equipment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    attributes: Mapped[list[EquipmentAttribute]] = relationship(
        back_populates="equipment",
        cascade="save-update, merge",
        foreign_keys=(
            "[EquipmentAttribute.project_id, EquipmentAttribute.revision_id, "
            "EquipmentAttribute.equipment_id]"
        ),
        order_by="EquipmentAttribute.attribute_key",
    )


class EquipmentAttribute(Base):
    __tablename__ = "equipment_attributes"
    __table_args__ = (
        UniqueConstraint("equipment_id", "attribute_key", name="uq_equipment_attributes_key"),
        UniqueConstraint("project_id", "id", name="uq_equipment_attributes_project_id_id"),
        ForeignKeyConstraint(
            ["project_id", "revision_id", "equipment_id"],
            ["equipment.project_id", "equipment.revision_id", "equipment.id"],
            name="fk_equipment_attributes_equipment",
        ),
        ForeignKeyConstraint(
            ["project_id", "inherited_from_attribute_id"],
            ["equipment_attributes.project_id", "equipment_attributes.id"],
            name="fk_equipment_attributes_inherited_from",
        ),
        CheckConstraint(
            "inherited_from_attribute_id IS NULL OR inherited_from_attribute_id <> id",
            name="ck_equipment_attributes_inherited_not_self",
        ),
        CheckConstraint(TYPED_VALUE_CHECK, name="ck_equipment_attributes_typed_value"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_equipment_attributes_confidence",
        ),
        CheckConstraint(
            "numeric_value IS NULL OR numeric_value NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name="ck_equipment_attributes_finite_numeric",
        ),
        Index("ix_equipment_attributes_project_revision", "project_id", "revision_id"),
        Index("ix_equipment_attributes_inherited_from", "inherited_from_attribute_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    equipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attribute_key: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[AttributeValueType] = mapped_column(attribute_value_type_enum)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric)
    integer_value: Mapped[int | None] = mapped_column(BigInteger)
    text_value: Mapped[str | None] = mapped_column(Text)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    unit: Mapped[str | None] = mapped_column(Text)
    information_state: Mapped[InformationState] = mapped_column(
        information_state_enum, server_default=text("'NOT_EXTRACTED'::model_information_state")
    )
    verification_state: Mapped[VerificationState] = mapped_column(
        verification_state_enum, server_default=text("'UNVERIFIED'::model_verification_state")
    )
    origin: Mapped[ValueOrigin | None] = mapped_column(value_origin_enum)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    inherited_from_attribute_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    equipment: Mapped[Equipment] = relationship(
        back_populates="attributes",
        foreign_keys=[project_id, revision_id, equipment_id],
    )
