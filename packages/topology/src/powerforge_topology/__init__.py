"""Electrical topology contracts.

Topology is a queryable graph owned by the engineering model. Visualization consumes
the model via the API and must not maintain a separate topology database.
"""

from powerforge_topology.enums import ConnectionDirection, ConnectionKind, ModelNodeKind

__all__ = ["ModelNodeKind", "ConnectionKind", "ConnectionDirection"]
