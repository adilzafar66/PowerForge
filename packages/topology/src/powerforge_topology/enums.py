from enum import StrEnum


class ModelNodeKind(StrEnum):
    EQUIPMENT_TERMINAL = "EQUIPMENT_TERMINAL"
    ELECTRICAL_NODE = "ELECTRICAL_NODE"


class ConnectionKind(StrEnum):
    ELECTRICAL = "ELECTRICAL"
    GROUNDING = "GROUNDING"
    OTHER = "OTHER"


class ConnectionDirection(StrEnum):
    UNDIRECTED = "UNDIRECTED"
    NOMINAL_FROM_TO = "NOMINAL_FROM_TO"
