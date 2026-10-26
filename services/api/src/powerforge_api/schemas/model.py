"""Manual canonical model inputs and explicit revision-scoped response contracts."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)

from powerforge_engineering_model import (
    AttributeValueType,
    EquipmentType,
    InformationState,
    LifecycleStatus,
    ValueOrigin,
    VerificationState,
)
from powerforge_topology import ConnectionDirection, ConnectionKind, ModelNodeKind


class ModelLifecycleFilter(StrEnum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"
    ALL = "ALL"

    def canonical(self) -> LifecycleStatus | None:
        return None if self == self.ALL else LifecycleStatus(self.value)


class ManualAction(BaseModel):
    """Optional empty lifecycle body; callers cannot inject audit/provenance metadata."""

    model_config = ConfigDict(extra="forbid")


class ManualUpdate(ManualAction):
    """An empty PATCH must not be interpreted as a manual review action."""

    @model_validator(mode="after")
    def require_supplied_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class EquipmentCreate(ManualAction):
    equipment_type: EquipmentType
    tag: str | None = None
    name: str | None = None
    description: str | None = None


class EquipmentUpdate(ManualUpdate):
    equipment_type: EquipmentType | None = Field(
        default=None, description="Omit to keep type; null is invalid."
    )
    tag: str | None = None
    name: str | None = None
    description: str | None = None

    @field_validator("equipment_type")
    @classmethod
    def nonnull_type(cls, value: EquipmentType | None) -> EquipmentType:
        if value is None:
            raise ValueError("equipment_type cannot be null")
        return value


class AttributeUpdate(ManualAction):
    information_state: Literal[
        InformationState.PRESENT,
        InformationState.UNKNOWN,
        InformationState.MISSING,
        InformationState.NOT_APPLICABLE,
    ]
    value: JsonValue = Field(
        default=None,
        description="Registry-validated value; decimal strings preserve input precision.",
    )
    unit: str | None = Field(
        default=None, description="Input unit; storage unit is registry-controlled."
    )


class NodeCreate(ManualAction):
    kind: ModelNodeKind
    equipment_id: UUID | None = None
    terminal_key: str | None = None
    label: str | None = None

    @model_validator(mode="after")
    def node_shape(self) -> Self:
        if self.kind == ModelNodeKind.EQUIPMENT_TERMINAL:
            if self.equipment_id is None or not self.terminal_key or not self.terminal_key.strip():
                raise ValueError(
                    "Equipment terminals require equipment_id and a nonblank terminal_key"
                )
        elif self.equipment_id is not None or self.terminal_key is not None:
            raise ValueError("Electrical nodes cannot have equipment_id or terminal_key")
        return self


class NodeUpdate(ManualUpdate):
    terminal_key: str | None = Field(
        default=None, description="Terminal nodes only. Omit to keep; null/blank is invalid."
    )
    label: str | None = None

    @field_validator("terminal_key")
    @classmethod
    def nonblank_key(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("terminal_key must be nonblank")
        return value


class ConnectionCreate(ManualAction):
    from_node_id: UUID
    to_node_id: UUID
    connection_kind: ConnectionKind = ConnectionKind.ELECTRICAL
    direction: ConnectionDirection = ConnectionDirection.UNDIRECTED
    phase_configuration: str | None = None
    nominal_voltage: Decimal | None = Field(
        default=None, description="Optional voltage input; normalized to kV by the service."
    )
    nominal_voltage_unit: str | None = Field(
        default=None, description="Input voltage unit; omitted means kV."
    )


class ConnectionUpdate(ManualUpdate):
    from_node_id: UUID | None = None
    to_node_id: UUID | None = None
    connection_kind: ConnectionKind | None = None
    direction: ConnectionDirection | None = None
    phase_configuration: str | None = None
    nominal_voltage: Decimal | None = Field(
        default=None, description="Omit to keep; null clears voltage and canonical unit."
    )
    nominal_voltage_unit: str | None = Field(
        default=None, description="Input unit; must accompany nominal_voltage."
    )

    @field_validator("from_node_id", "to_node_id", "connection_kind", "direction")
    @classmethod
    def nonnull_field(cls, value):
        if value is None:
            raise ValueError("Field cannot be null; omit to keep its current value")
        return value

    @model_validator(mode="after")
    def unit_requires_voltage(self) -> Self:
        if (
            "nominal_voltage_unit" in self.model_fields_set
            and "nominal_voltage" not in self.model_fields_set
        ):
            raise ValueError("nominal_voltage_unit requires nominal_voltage")
        return self


class CanonicalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    revision_id: UUID
    created_at: datetime
    created_by: UUID | None
    updated_at: datetime
    updated_by: UUID | None


class LifecycleResponse(CanonicalResponse):
    lifecycle_status: LifecycleStatus
    origin: ValueOrigin
    verification_state: VerificationState
    removed_at: datetime | None
    removed_by: UUID | None


class EquipmentResponse(LifecycleResponse):
    lineage_id: UUID
    equipment_type: EquipmentType
    tag: str | None
    name: str | None
    description: str | None
    inherited_from_equipment_id: UUID | None


class AttributeResponse(CanonicalResponse):
    equipment_id: UUID
    attribute_key: str
    value_type: AttributeValueType
    numeric_value: Decimal | None
    integer_value: int | None
    text_value: str | None
    boolean_value: bool | None
    unit: str | None
    information_state: InformationState
    verification_state: VerificationState
    origin: ValueOrigin | None
    confidence: Decimal | None
    inherited_from_attribute_id: UUID | None

    @field_serializer("integer_value", when_used="json")
    def serialize_integer_value(self, value: int | None) -> str | None:
        """Keep BIGINT values exact in JSON consumers, including browsers."""
        return str(value) if value is not None else None


class NodeResponse(LifecycleResponse):
    kind: ModelNodeKind
    equipment_id: UUID | None
    terminal_key: str | None
    label: str | None
    inherited_from_node_id: UUID | None


class ConnectionResponse(LifecycleResponse):
    from_node_id: UUID
    to_node_id: UUID
    connection_kind: ConnectionKind
    direction: ConnectionDirection
    phase_configuration: str | None
    nominal_voltage: Decimal | None
    nominal_voltage_unit: str | None
    confidence: Decimal | None
    inherited_from_connection_id: UUID | None


class EquipmentListResponse(BaseModel):
    items: list[EquipmentResponse]


class AttributeListResponse(BaseModel):
    items: list[AttributeResponse]


class NodeListResponse(BaseModel):
    items: list[NodeResponse]


class ConnectionListResponse(BaseModel):
    items: list[ConnectionResponse]
