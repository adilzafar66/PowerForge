"""Small domain and boundary checks; voltage arithmetic remains owned by Phase 5A."""

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from powerforge_api.exceptions import InvalidTopology
from powerforge_api.services.topology_service import normalize_nominal_voltage
from powerforge_topology import ConnectionDirection, ConnectionKind, ModelNodeKind


def test_exact_topology_vocabulary_and_pure_package():
    assert set(ModelNodeKind) == {"EQUIPMENT_TERMINAL", "ELECTRICAL_NODE"}
    assert set(ConnectionKind) == {"ELECTRICAL", "GROUNDING", "OTHER"}
    assert set(ConnectionDirection) == {"UNDIRECTED", "NOMINAL_FROM_TO"}
    root = Path(__file__).resolve().parents[1] / "packages/topology/src"
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules = (
                [n.name for n in node.names]
                if isinstance(node, ast.Import)
                else [node.module]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert all(m == "enum" or m.startswith("powerforge_topology") for m in modules)


def test_connection_voltage_uses_canonical_decimal():
    assert normalize_nominal_voltage("600", "V") == (Decimal("0.6"), "kV")
    assert normalize_nominal_voltage("0.001", "MV") == (Decimal("1"), "kV")
    assert normalize_nominal_voltage(None) == (None, None)
    for value, unit in [(True, "kV"), (0, "kV"), ("NaN", "kV"), (1, "A"), (None, "V")]:
        with pytest.raises(InvalidTopology):
            normalize_nominal_voltage(value, unit)
