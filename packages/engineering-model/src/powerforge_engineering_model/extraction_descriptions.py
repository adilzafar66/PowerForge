"""Registry-owned classification guidance for Phase 6R prompt projections."""

from types import MappingProxyType

from powerforge_engineering_model.enums import EquipmentType

DESCRIPTION_VERSION = "equipment-descriptions-v2"
ATTRIBUTE_DESCRIPTION_VERSION = "attribute-descriptions-v1"

EQUIPMENT_DESCRIPTIONS = MappingProxyType(
    {
        EquipmentType.UTILITY_SOURCE: "Utility supply or grid equivalent at the service point.",
        EquipmentType.SYNCHRONOUS_GENERATOR: "Synchronous rotating machine supplying power.",
        EquipmentType.TWO_WINDING_TRANSFORMER: "Transformer with primary and secondary windings.",
        EquipmentType.BUS: (
            "Bus or bus assembly representing a switchboard, panel, or switchgear section. "
            "Assembly tags and assembly ratings belong here, separately from branch devices."
        ),
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

# Registry keys remain authoritative. This metadata explains their meanings to
# extraction providers and does not execute engineering mappings or inference.
ATTRIBUTE_DESCRIPTIONS = MappingProxyType(
    {
        "model": "Equipment series or model identifier. Distinguish the ordering/catalog number.",
        "catalog_number": (
            "Ordering identifier specifying a product configuration. Preserve incomplete "
            "characters. Do not substitute a series name or deduce unspecified options."
        ),
        "manufacturer": (
            "Manufacturer of this equipment occurrence. A page footer or assembly vendor "
            "alone supports contextual inference unless it explicitly identifies this device."
        ),
        "breaker_type": (
            "Engineering breaker class from the permitted enum. An identified product family "
            "may support inference. Neither ampere rating nor absence of a designation proves a "
            "class."
        ),
        "trip_unit_model": (
            "Identifier of the trip unit. Protection-function designations describe separate "
            "context, not a second model or a condition on the identifier."
        ),
        "trip_unit_type": (
            "Trip technology, such as ELECTRONIC or THERMAL_MAGNETIC. A trip model name "
            "does not literally report the technology. Product-model knowledge is an inference."
        ),
        "frame_rating": (
            "Maximum continuous-current rating of the breaker frame. A bare device ampere "
            "rating does not establish frame, sensor, plug, or trip rating."
        ),
        "trip_rating": (
            "Rated trip current for the specified trip configuration. Distinguish frame size, "
            "sensor current, plug size, and adjustable pickup. Preserve ambiguous ratings as "
            "source facts."
        ),
        "sensor_rating": (
            "Nominal current of the electronic-trip sensing element. It may differ from "
            "frame rating, rating plug, and pickup. Require support for the specific concept."
        ),
        "rating_plug": (
            "Current rating of the installed trip-unit plug. A device ampere rating alone "
            "does not identify a rating plug."
        ),
        "long_time_pickup": (
            "Long-time protection pickup current or explicitly supported setting. Do not "
            "substitute frame, sensor, plug, or bare device current."
        ),
        "short_circuit_current_rating": (
            "Assembly or equipment short-circuit current rating, usually RMS symmetrical. "
            "An SC/SCCR designation can report this. Distinguish breaking capacity, peak current, "
            "bus bracing, and timed short-time withstand."
        ),
        "short_time_withstand_current": (
            "RMS current that equipment withstands for a specified short duration. "
            "Bus bracing or a short-circuit level alone does not establish a timed withstand "
            "rating."
        ),
        "short_time_withstand_duration": (
            "Duration associated with the short-time withstand current. Never invent it from a "
            "rating."
        ),
        "peak_withstand_current": (
            "Peak instantaneous withstand current. Distinguish RMS symmetrical fault ratings. "
            "Do not convert between peak and RMS without a justified separately identified "
            "inference."
        ),
        "standard": (
            "Registry ANSI/IEC classification. UL and CSA product-standard designations are "
            "separate source facts. Preserve them as unmapped when this enum does not represent "
            "them."
        ),
        "nominal_voltage": (
            "Nominal bus voltage, line-to-line for a three-phase system. Preserve a combined "
            "phase-neutral/line-line expression. Any derived scalar needs an inference with "
            "the original expression and explanation."
        ),
        "rated_voltage": (
            "Rated equipment voltage. Preserve combined voltage expressions. A chosen "
            "scalar interpretation must state its source expression and justification."
        ),
        "phase_count": (
            "Number of phases. An explicit phase notation supplies the count. "
            "The notation itself is not a qualifier or an operating restriction."
        ),
    }
)

EQUIPMENT_EXTRACTION_GUIDANCE_VERSION = "equipment-extraction-guidance-v1"
ATTRIBUTE_NOTES_VERSION = "registry-attribute-notes-d0-v1"

EQUIPMENT_EXTRACTION_GUIDANCE = MappingProxyType(
    {
        EquipmentType.LV_BREAKER: (
            "Keep frame, sensor, rating-plug, trip and long-time pickup currents distinct. "
            "An unlabeled ampere rating may be meaningful even when its "
            "specific function is unclear. "
            "Distinguish breaker series, ordering identifier, trip-unit model and protection "
            "functions. A specific model can support an inference about trip technology or "
            "breaker class. An absent designation cannot establish either. Use UL or CSA "
            "references as product-standard evidence unless the source independently establishes "
            "the ANSI/IEC classification."
        ),
        EquipmentType.BUS: (
            "Associate assembly ratings and enclosure data with the bus assembly. Associate "
            "branch-device ratings with their respective devices. "
            "Distinguish SC/SCCR, interrupting "
            "capacity, bus bracing, peak withstand, and timed withstand. Bracing alone does not "
            "establish a timed rating."
        ),
        EquipmentType.SYNCHRONOUS_GENERATOR: (
            "Keep direct and quadrature axes, transient and subtransient quantities, and "
            "open-circuit and short-circuit time constants distinct. Use the row, heading, "
            "and reference base to distinguish machine-base reactances from values reported "
            "on another base. Preserve test conditions and distinguish armature resistance "
            "from other winding resistances."
        ),
        EquipmentType.TWO_WINDING_TRANSFORMER: (
            "Keep primary and secondary values, nominal and tap voltages, base and fan-cooled "
            "capacity, and positive- and zero-sequence impedance distinct. Use nameplate headings "
            "and winding context to associate each value with the correct winding or rating. "
            "Preserve paired secondary voltages and impedance ranges as reported."
        ),
    }
)
