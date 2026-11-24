"""Superseded registry note values needed to reconstruct existing Stage 2 catalogs."""

from types import MappingProxyType

# A stored None means the historical catalog carried a null note.
LEGACY_ATTRIBUTE_NOTES = MappingProxyType(
    {
        ("UTILITY_SOURCE", "nominal_voltage"): "Usually 24.94kV or 12.47kV",
        ("UTILITY_SOURCE", "phase_count"): "Usually 3",
        ("SYNCHRONOUS_GENERATOR", "manufacturer"): None,
        ("SYNCHRONOUS_GENERATOR", "model"): None,
        ("SYNCHRONOUS_GENERATOR", "phase_count"): "Typically 3",
        ("SYNCHRONOUS_GENERATOR", "rated_voltage"): None,
        ("SYNCHRONOUS_GENERATOR", "rated_power_factor"): "pf Ranges from 0-1",
        (
            "SYNCHRONOUS_GENERATOR",
            "reactance_base_power",
        ): "Required if reactance values are based on it and it's different than rated value",
        (
            "SYNCHRONOUS_GENERATOR",
            "reactance_base_voltage",
        ): "Required if reactance values are based on it and it's different than rated value",
        ("TWO_WINDING_TRANSFORMER", "manufacturer"): None,
        ("TWO_WINDING_TRANSFORMER", "model"): None,
        ("BUS", "manufacturer"): None,
        ("BUS", "model"): None,
        ("BUS", "nominal_voltage"): None,
        ("BUS", "phase_count"): None,
        ("BUS", "short_circuit_current_rating"): "Typically RMS symmetrical current",
        ("BUS", "short_time_withstand_current"): "Typically RMS symmetrical",
        ("BUS", "short_time_withstand_duration"): None,
        ("BUS", "peak_withstand_current"): "Peak current, not RMS",
        ("BUS", "working_distance"): "If bus_type is given, working_distance is usually inferred.",
        ("LV_BREAKER", "standard"): None,
        ("LV_BREAKER", "manufacturer"): "Required to determine trip curve.",
        ("LV_BREAKER", "model"): "Required to determine trip curve.",
        ("LV_BREAKER", "catalog_number"): None,
        ("LV_BREAKER", "breaker_type"): None,
        ("LV_BREAKER", "rated_voltage"): None,
        (
            "LV_BREAKER",
            "frame_rating",
        ): "Ampere rating of the breaker frame; Deduced if catalog_number is provided.",
        (
            "LV_BREAKER",
            "sensor_rating",
        ): "Ampere rating of the trip unit sensor; Required for electronic trip breakers.",
        ("LV_BREAKER", "rating_plug"): "Size of the trip unit plug",
        (
            "LV_BREAKER",
            "trip_rating",
        ): (
            "Trip amps / long-time pickup for thermal magnetic breakers; "
            "Required for thermal magnetic breakers."
        ),
        (
            "LV_BREAKER",
            "long_time_pickup",
        ): "Long-time pickup for electronic trip breakers; Required for electronic trip breakers.",
        (
            "LV_BREAKER",
            "interrupting_rating",
        ): "Interrupting rating is usually deduced from the breaker model + rated voltage.",
        ("LV_BREAKER", "trip_unit_type"): None,
        (
            "LV_BREAKER",
            "trip_unit_model",
        ): "Required for electronic trip breakers; Required to determine trip curve.",
        ("HV_BREAKER", "standard"): None,
        ("HV_BREAKER", "manufacturer"): None,
        ("HV_BREAKER", "model"): None,
        ("HV_BREAKER", "catalog_number"): None,
        ("HV_BREAKER", "breaker_type"): None,
        ("HV_BREAKER", "rated_voltage"): None,
        (
            "HV_BREAKER",
            "short_circuit_breaking_current",
        ): (
            "Rated short-circuit interrupting rating - ANSI\nRated short-circuit "
            "breaking current - IEC Can be deduced from manufacturer + model."
        ),
        (
            "HV_BREAKER",
            "short_circuit_making_current",
        ): (
            "Rated closing-and-latching current - ANSI\nRated short-circuit "
            "making current - IEC Can be deduced from manufacturer + model."
        ),
        (
            "HV_BREAKER",
            "short_time_withstand_current",
        ): (
            "Short-time current-carrying capability - ANSI\nRated short-time "
            "withstand current - IEC Can be deduced from manufacturer + model."
        ),
        (
            "HV_BREAKER",
            "short_time_withstand_duration",
        ): (
            "Permissible tripping delay / short-time duration - ANSI\nRated "
            "short-circuit duration - IEC Can be deduced from manufacturer + "
            "model."
        ),
        (
            "HV_BREAKER",
            "rated_interrupting_time",
        ): (
            "Rated interrupting time - ANSI\nRated Break time - IEC Can be "
            "deduced from manufacturer + model."
        ),
        (
            "HV_BREAKER",
            "opening_time",
        ): (
            "Contact-parting time - ANSI\nRated opening time - IEC Can be deduced "
            "from manufacturer + model."
        ),
        ("RECLOSER", "manufacturer"): None,
        ("RECLOSER", "model"): None,
        ("RECLOSER", "rated_voltage"): None,
        ("RECLOSER", "short_time_withstand_current"): None,
        ("RECLOSER", "short_time_withstand_duration"): None,
        ("OVERCURRENT_RELAY", "manufacturer"): None,
        ("OVERCURRENT_RELAY", "model"): None,
        ("OVERCURRENT_RELAY", "nominal_current_input"): "Usually 1 A or 5 A CT input",
        ("OVERCURRENT_RELAY", "minimum_relay_operating_time"): "If explicitly published/relevant",
        ("OVERCURRENT_RELAY", "trip_output_operating_time"): "If separately published",
        ("FUSE", "manufacturer"): "Required to determine trip curve.",
        ("FUSE", "model"): "Required to determine trip curve.",
        ("FUSE", "catalog_number"): None,
        ("FUSE", "rated_voltage"): None,
        ("FUSE", "current_rating"): "Can be deduced from catalog number.",
        ("FUSE", "interrupting_rating"): "Can be deduced from manufacturer + model.",
        ("FUSE", "fuse_class"): "Can be deduced from manufacturer + model.",
        ("FUSE", "fuse_speed"): "Can be deduced from manufacturer + model.",
        ("SINGLE_THROW_SWITCH", "rated_voltage"): None,
        ("SINGLE_THROW_SWITCH", "short_time_withstand_current"): None,
        ("SINGLE_THROW_SWITCH", "short_time_withstand_duration"): None,
        (
            "SINGLE_THROW_SWITCH",
            "peak_withstand_current",
        ): (
            "Peak instantaneous current withstand capability, including DC "
            "offset effects; do not interpret as RMS symmetrical current."
        ),
        ("SINGLE_THROW_SWITCH", "short_circuit_current_rating"): None,
        ("DOUBLE_THROW_SWITCH", "manufacturer"): None,
        ("DOUBLE_THROW_SWITCH", "model"): None,
        ("DOUBLE_THROW_SWITCH", "rated_voltage"): None,
        ("DOUBLE_THROW_SWITCH", "short_time_withstand_current"): None,
        ("DOUBLE_THROW_SWITCH", "short_time_withstand_duration"): None,
        (
            "DOUBLE_THROW_SWITCH",
            "peak_withstand_current",
        ): (
            "Peak instantaneous current withstand capability, including DC "
            "offset effects; do not interpret as RMS symmetrical current."
        ),
        ("DOUBLE_THROW_SWITCH", "short_circuit_current_rating"): None,
        ("CABLE", "manufacturer"): None,
        ("CABLE", "model"): None,
        ("CABLE", "rated_voltage"): None,
        ("CT", "manufacturer"): None,
        ("CT", "model"): None,
        ("INDUCTION_MOTOR", "manufacturer"): None,
        ("INDUCTION_MOTOR", "model"): None,
        ("INDUCTION_MOTOR", "rated_voltage"): None,
        ("INDUCTION_MOTOR", "phase_count"): None,
        ("STATIC_LOAD", "rated_voltage"): None,
        (
            "STATIC_LOAD",
            "rated_active_power",
        ): "Alternative load-power representation; see Requirement Rules.",
        (
            "STATIC_LOAD",
            "rated_reactive_power",
        ): "Alternative load-power representation; see Requirement Rules.",
        (
            "STATIC_LOAD",
            "rated_apparent_power",
        ): "Alternative load-power representation; see Requirement Rules.",
        (
            "STATIC_LOAD",
            "power_factor",
        ): "Required with rated_apparent_power when using the kVA + PF representation.",
        ("STATIC_LOAD", "phase_count"): None,
        ("LUMPED_LOAD", "manufacturer"): None,
        ("LUMPED_LOAD", "model"): None,
        ("LUMPED_LOAD", "rated_voltage"): None,
        ("LUMPED_LOAD", "phase_count"): None,
        ("CAPACITOR", "manufacturer"): None,
        ("CAPACITOR", "model"): None,
        ("CAPACITOR", "rated_voltage"): None,
        ("CAPACITOR", "phase_count"): None,
        ("CAPACITOR", "short_circuit_current_rating"): None,
        ("REACTOR", "manufacturer"): None,
        ("REACTOR", "model"): None,
        ("REACTOR", "phase_count"): None,
        ("REACTOR", "rated_voltage"): None,
        ("REACTOR", "short_time_withstand_current"): None,
        ("REACTOR", "short_time_withstand_duration"): None,
        ("REACTOR", "peak_withstand_current"): None,
        ("VFD", "manufacturer"): None,
        ("VFD", "model"): None,
        ("VFD", "short_circuit_current_rating"): None,
        ("UPS", "manufacturer"): None,
        ("UPS", "model"): None,
    }
)
