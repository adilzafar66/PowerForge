from enum import StrEnum


class EquipmentType(StrEnum):
    """Initial equipment types. Additional types may be added without a new table per type."""

    UTILITY_SOURCE = "UtilitySource"
    GENERATOR = "Generator"
    TRANSFORMER = "Transformer"
    BUS = "Bus"
    SWITCHGEAR = "Switchgear"
    MCC = "MCC"
    PANEL = "Panel"
    BREAKER = "Breaker"
    FUSE = "Fuse"
    DISCONNECT = "Disconnect"
    SWITCH = "Switch"
    CABLE = "Cable"
    MOTOR = "Motor"
    LOAD = "Load"
    CONNECTION = "Connection"


class InformationState(StrEnum):
    """Presence / quality of an attribute. Do not use null alone for every situation."""

    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EXTRACTED = "NOT_EXTRACTED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONFLICTING = "CONFLICTING"
    INFERRED = "INFERRED"
    VERIFIED = "VERIFIED"


class VerificationState(StrEnum):
    """Safety states for extracted vs engineer-confirmed information.

    Never silently promote AI_EXTRACTED to ENGINEER_VERIFIED.
    """

    AI_EXTRACTED = "AI_EXTRACTED"
    SYSTEM_VALIDATED = "SYSTEM_VALIDATED"
    ENGINEER_REVIEWED = "ENGINEER_REVIEWED"
    ENGINEER_VERIFIED = "ENGINEER_VERIFIED"
