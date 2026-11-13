"""Registry-owned classification guidance for Phase 6R prompt projections."""

from types import MappingProxyType

from powerforge_engineering_model.enums import EquipmentType

DESCRIPTION_VERSION = "equipment-descriptions-v1"

EQUIPMENT_DESCRIPTIONS = MappingProxyType(
    {
        EquipmentType.UTILITY_SOURCE: "Utility supply or grid equivalent at the service point.",
        EquipmentType.SYNCHRONOUS_GENERATOR: "Synchronous rotating machine supplying power.",
        EquipmentType.TWO_WINDING_TRANSFORMER: "Transformer with primary and secondary windings.",
        EquipmentType.BUS: "Common conductor or bus section serving multiple circuits.",
        EquipmentType.LV_BREAKER: "Circuit breaker explicitly identified for low-voltage service.",
        EquipmentType.HV_BREAKER: "Circuit breaker identified for medium- or high-voltage service.",
        EquipmentType.RECLOSER: "Protective interrupter that opens and automatically recloses.",
        EquipmentType.OVERCURRENT_RELAY: "Relay sensing overcurrent and issuing a protective trip.",
        EquipmentType.FUSE: "Overcurrent protective device with a fusible element.",
        EquipmentType.SINGLE_THROW_SWITCH: "Switch with one available connected position per pole.",
        EquipmentType.DOUBLE_THROW_SWITCH: "Switch selecting between two connected positions.",
        EquipmentType.CABLE: "Electrical cable or cable run described by its construction.",
        EquipmentType.CT: "Current transformer for measurement or protection.",
        EquipmentType.INDUCTION_MOTOR: "AC induction motor delivering mechanical shaft power.",
        EquipmentType.STATIC_LOAD: "Individual non-rotating electrical load or equivalent.",
        EquipmentType.LUMPED_LOAD: "Aggregate representation of multiple loads at a common point.",
        EquipmentType.CAPACITOR: "Capacitor or capacitor bank used as power-system equipment.",
        EquipmentType.REACTOR: "Inductive reactor identified as power-system equipment.",
        EquipmentType.VFD: "Drive that varies electrical frequency to control an AC motor.",
        EquipmentType.UPS: "Uninterruptible power supply that maintains power during input loss.",
    }
)
