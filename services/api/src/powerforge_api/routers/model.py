"""Revision-scoped manual engineering model API; services own all canonical writes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from powerforge_api.db import get_session
from powerforge_api.routers.errors import model_api_errors
from powerforge_api.schemas.model import (
    AttributeListResponse,
    AttributeResponse,
    AttributeUpdate,
    ConnectionCreate,
    ConnectionListResponse,
    ConnectionResponse,
    ConnectionUpdate,
    EquipmentCreate,
    EquipmentListResponse,
    EquipmentResponse,
    EquipmentUpdate,
    ManualAction,
    ModelLifecycleFilter,
    NodeCreate,
    NodeListResponse,
    NodeResponse,
    NodeUpdate,
)
from powerforge_api.services.engineering_model_service import EngineeringModelService
from powerforge_api.services.topology_service import TopologyService
from powerforge_engineering_model import EquipmentType
from powerforge_topology import ModelNodeKind

router = APIRouter(
    prefix="/api/projects/{project_id}/revisions/{revision_id}",
    tags=["engineering-model"],
)
SessionDep = Annotated[Session, Depends(get_session)]
LifecycleQuery = Annotated[
    ModelLifecycleFilter,
    Query(description="ACTIVE by default; REMOVED for restoration; ALL includes both."),
]


@router.get("/equipment", response_model=EquipmentListResponse, summary="List revision equipment")
def list_equipment(
    project_id: UUID,
    revision_id: UUID,
    session: SessionDep,
    lifecycle_status: LifecycleQuery = ModelLifecycleFilter.ACTIVE,
    equipment_type: Annotated[
        EquipmentType | None, Query(description="Canonical registry equipment type.")
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Case-insensitive tag/name/description substring; blank is ignored."),
    ] = None,
) -> EquipmentListResponse:
    with model_api_errors():
        return EquipmentListResponse(
            items=EngineeringModelService(session).list_equipment(
                project_id,
                revision_id,
                lifecycle_status=lifecycle_status.canonical(),
                equipment_type=equipment_type,
                search=search,
            )
        )


@router.post(
    "/equipment",
    response_model=EquipmentResponse,
    status_code=201,
    summary="Create manual equipment",
)
def create_equipment(
    project_id: UUID,
    revision_id: UUID,
    body: EquipmentCreate,
    session: SessionDep,
) -> EquipmentResponse:
    with model_api_errors():
        return EquipmentResponse.model_validate(
            EngineeringModelService(session).create_equipment(
                project_id,
                revision_id,
                **body.model_dump(),
            )
        )


@router.get(
    "/equipment/{equipment_id}", response_model=EquipmentResponse, summary="Get revision equipment"
)
def get_equipment(
    project_id: UUID,
    revision_id: UUID,
    equipment_id: UUID,
    session: SessionDep,
) -> EquipmentResponse:
    with model_api_errors():
        return EquipmentResponse.model_validate(
            EngineeringModelService(session).get_equipment(
                project_id,
                revision_id,
                equipment_id,
            )
        )


@router.patch(
    "/equipment/{equipment_id}", response_model=EquipmentResponse, summary="Edit manual equipment"
)
def update_equipment(
    project_id: UUID,
    revision_id: UUID,
    equipment_id: UUID,
    body: EquipmentUpdate,
    session: SessionDep,
) -> EquipmentResponse:
    with model_api_errors():
        return EquipmentResponse.model_validate(
            EngineeringModelService(session).update_equipment(
                project_id,
                revision_id,
                equipment_id,
                **body.model_dump(exclude_unset=True),
            )
        )


@router.get(
    "/equipment/{equipment_id}/attributes",
    response_model=AttributeListResponse,
    summary="List canonical attributes in registry order",
)
def list_attributes(
    project_id: UUID,
    revision_id: UUID,
    equipment_id: UUID,
    session: SessionDep,
) -> AttributeListResponse:
    with model_api_errors():
        return AttributeListResponse(
            items=EngineeringModelService(session).get_equipment_attributes(
                project_id,
                revision_id,
                equipment_id,
            )
        )


@router.put(
    "/equipment/{equipment_id}/attributes/{attribute_key}",
    response_model=AttributeResponse,
    summary="Set manual canonical attribute state and value",
)
def set_attribute(
    project_id: UUID,
    revision_id: UUID,
    equipment_id: UUID,
    attribute_key: str,
    body: AttributeUpdate,
    session: SessionDep,
) -> AttributeResponse:
    with model_api_errors():
        return AttributeResponse.model_validate(
            EngineeringModelService(session).set_attribute(
                project_id,
                revision_id,
                equipment_id,
                attribute_key,
                body.information_state,
                value=body.value,
                input_unit=body.unit,
            )
        )


@router.post(
    "/nodes",
    response_model=NodeResponse,
    status_code=201,
    summary="Create a manual terminal or electrical node",
)
def create_node(
    project_id: UUID,
    revision_id: UUID,
    body: NodeCreate,
    session: SessionDep,
) -> NodeResponse:
    with model_api_errors():
        service = TopologyService(session)
        if body.kind == ModelNodeKind.EQUIPMENT_TERMINAL:
            row = service.create_terminal(
                project_id,
                revision_id,
                body.equipment_id,
                body.terminal_key,
                label=body.label,
            )
        else:
            row = service.create_electrical_node(project_id, revision_id, label=body.label)
        return NodeResponse.model_validate(row)


@router.post(
    "/connections",
    response_model=ConnectionResponse,
    status_code=201,
    summary="Create a manual connection between revision nodes",
)
def create_connection(
    project_id: UUID,
    revision_id: UUID,
    body: ConnectionCreate,
    session: SessionDep,
) -> ConnectionResponse:
    values = body.model_dump()
    values["input_unit"] = values.pop("nominal_voltage_unit")
    with model_api_errors():
        return ConnectionResponse.model_validate(
            TopologyService(session).create_connection(
                project_id,
                revision_id,
                **values,
            )
        )


@router.patch(
    "/connections/{connection_id}",
    response_model=ConnectionResponse,
    summary="Edit or rewire a manual connection",
)
def update_connection(
    project_id: UUID,
    revision_id: UUID,
    connection_id: UUID,
    body: ConnectionUpdate,
    session: SessionDep,
) -> ConnectionResponse:
    values = body.model_dump(exclude_unset=True)
    if "nominal_voltage_unit" in values:
        values["input_unit"] = values.pop("nominal_voltage_unit")
    with model_api_errors():
        return ConnectionResponse.model_validate(
            TopologyService(session).update_connection(
                project_id,
                revision_id,
                connection_id,
                **values,
            )
        )


@router.patch(
    "/nodes/{node_id}", response_model=NodeResponse, summary="Edit a terminal key or node label"
)
def update_node(
    project_id: UUID,
    revision_id: UUID,
    node_id: UUID,
    body: NodeUpdate,
    session: SessionDep,
) -> NodeResponse:
    with model_api_errors():
        return NodeResponse.model_validate(
            TopologyService(session).update_node(
                project_id,
                revision_id,
                node_id,
                **body.model_dump(exclude_unset=True),
            )
        )


@router.get("/nodes", response_model=NodeListResponse, summary="List revision nodes")
def list_nodes(
    project_id: UUID,
    revision_id: UUID,
    session: SessionDep,
    lifecycle_status: LifecycleQuery = ModelLifecycleFilter.ACTIVE,
) -> NodeListResponse:
    with model_api_errors():
        return NodeListResponse(
            items=TopologyService(session).list_nodes(
                project_id,
                revision_id,
                lifecycle_status=lifecycle_status.canonical(),
            )
        )


@router.get(
    "/connections", response_model=ConnectionListResponse, summary="List revision connections"
)
def list_connections(
    project_id: UUID,
    revision_id: UUID,
    session: SessionDep,
    lifecycle_status: LifecycleQuery = ModelLifecycleFilter.ACTIVE,
) -> ConnectionListResponse:
    with model_api_errors():
        return ConnectionListResponse(
            items=TopologyService(session).list_connections(
                project_id,
                revision_id,
                lifecycle_status=lifecycle_status.canonical(),
            )
        )


@router.post(
    "/equipment/{equipment_id}/remove", response_model=EquipmentResponse, summary="Remove equipment"
)
def remove_equipment(
    project_id: UUID,
    revision_id: UUID,
    equipment_id: UUID,
    session: SessionDep,
    body: ManualAction | None = None,
) -> EquipmentResponse:
    with model_api_errors():
        return EquipmentResponse.model_validate(
            EngineeringModelService(session).remove_equipment(
                project_id,
                revision_id,
                equipment_id,
            )
        )


@router.post(
    "/equipment/{equipment_id}/restore",
    response_model=EquipmentResponse,
    summary="Restore equipment",
)
def restore_equipment(
    project_id: UUID,
    revision_id: UUID,
    equipment_id: UUID,
    session: SessionDep,
    body: ManualAction | None = None,
) -> EquipmentResponse:
    with model_api_errors():
        return EquipmentResponse.model_validate(
            EngineeringModelService(session).restore_equipment(
                project_id,
                revision_id,
                equipment_id,
            )
        )


@router.post("/nodes/{node_id}/remove", response_model=NodeResponse, summary="Remove node")
def remove_node(
    project_id: UUID,
    revision_id: UUID,
    node_id: UUID,
    session: SessionDep,
    body: ManualAction | None = None,
) -> NodeResponse:
    with model_api_errors():
        return NodeResponse.model_validate(
            TopologyService(session).remove_node(
                project_id,
                revision_id,
                node_id,
            )
        )


@router.post("/nodes/{node_id}/restore", response_model=NodeResponse, summary="Restore node")
def restore_node(
    project_id: UUID,
    revision_id: UUID,
    node_id: UUID,
    session: SessionDep,
    body: ManualAction | None = None,
) -> NodeResponse:
    with model_api_errors():
        return NodeResponse.model_validate(
            TopologyService(session).restore_node(
                project_id,
                revision_id,
                node_id,
            )
        )


@router.post(
    "/connections/{connection_id}/remove",
    response_model=ConnectionResponse,
    summary="Remove connection",
)
def remove_connection(
    project_id: UUID,
    revision_id: UUID,
    connection_id: UUID,
    session: SessionDep,
    body: ManualAction | None = None,
) -> ConnectionResponse:
    with model_api_errors():
        return ConnectionResponse.model_validate(
            TopologyService(session).remove_connection(
                project_id,
                revision_id,
                connection_id,
            )
        )


@router.post(
    "/connections/{connection_id}/restore",
    response_model=ConnectionResponse,
    summary="Restore connection",
)
def restore_connection(
    project_id: UUID,
    revision_id: UUID,
    connection_id: UUID,
    session: SessionDep,
    body: ManualAction | None = None,
) -> ConnectionResponse:
    with model_api_errors():
        return ConnectionResponse.model_validate(
            TopologyService(session).restore_connection(
                project_id,
                revision_id,
                connection_id,
            )
        )
