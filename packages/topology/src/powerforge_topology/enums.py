from enum import StrEnum


class NodeKind(StrEnum):
    BUS = "bus"
    EQUIPMENT_TERMINAL = "equipment_terminal"
    ELECTRICAL_NODE = "electrical_node"
