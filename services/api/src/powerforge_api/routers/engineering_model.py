"""Static engineering registry. No database, worker, or provider dependency."""

from fastapi import APIRouter

from powerforge_api.schemas.engineering_model import (
    AttributeDefinitionResponse,
    EquipmentDefinitionResponse,
    RegistryResponse,
)
from powerforge_engineering_model import REGISTRY, supported_input_units

router = APIRouter(prefix="/api/engineering-model", tags=["engineering-model"])


@router.get("/registry", response_model=RegistryResponse)
def get_registry() -> RegistryResponse:
    return RegistryResponse(
        registry_version=REGISTRY.registry_version,
        equipment_types=tuple(
            EquipmentDefinitionResponse(
                key=equipment.key,
                display_name=equipment.display_name,
                attributes=tuple(
                    AttributeDefinitionResponse.model_validate(attribute).model_copy(
                        update={
                            "supported_input_units": supported_input_units(
                                equipment.key, attribute.key
                            ),
                        }
                    )
                    for attribute in equipment.attributes
                ),
                requirements=equipment.requirements,
            )
            for equipment in REGISTRY.equipment_types
        ),
        requirement_rules=REGISTRY.requirement_rules,
        unit_families=REGISTRY.unit_families,
    )
