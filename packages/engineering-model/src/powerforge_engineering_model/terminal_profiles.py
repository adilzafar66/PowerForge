"""Code-owned physical terminal roles, separate from frozen attribute registry-v1."""

from types import MappingProxyType

from powerforge_engineering_model.enums import EquipmentType

TERMINAL_PROFILES = MappingProxyType(
    {
        EquipmentType.UTILITY_SOURCE: ("OUTPUT",),
        EquipmentType.SYNCHRONOUS_GENERATOR: ("OUTPUT",),
        EquipmentType.TWO_WINDING_TRANSFORMER: ("PRIMARY", "SECONDARY"),
        EquipmentType.BUS: ("BUS",),
        EquipmentType.LV_BREAKER: ("INPUT", "OUTPUT"),
        EquipmentType.HV_BREAKER: ("INPUT", "OUTPUT"),
        EquipmentType.RECLOSER: ("INPUT", "OUTPUT"),
        EquipmentType.OVERCURRENT_RELAY: (),
        EquipmentType.FUSE: ("INPUT", "OUTPUT"),
        EquipmentType.SINGLE_THROW_SWITCH: ("INPUT", "OUTPUT"),
        EquipmentType.DOUBLE_THROW_SWITCH: ("SOURCE_1", "SOURCE_2", "COMMON"),
        EquipmentType.CABLE: ("END_A", "END_B"),
        EquipmentType.CT: ("INPUT", "OUTPUT"),
        EquipmentType.INDUCTION_MOTOR: ("INPUT",),
        EquipmentType.STATIC_LOAD: ("INPUT",),
        EquipmentType.LUMPED_LOAD: ("INPUT",),
        EquipmentType.CAPACITOR: ("INPUT",),
        EquipmentType.REACTOR: ("INPUT", "OUTPUT"),
        EquipmentType.VFD: ("INPUT", "OUTPUT"),
        EquipmentType.UPS: ("INPUT", "OUTPUT"),
    }
)


def terminal_profile(equipment_type: EquipmentType | str) -> tuple[str, ...]:
    return TERMINAL_PROFILES[EquipmentType(equipment_type)]
