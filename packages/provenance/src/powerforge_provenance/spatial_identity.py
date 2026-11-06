"""Packaged identities for the new pure contracts; accepted resources are untouched."""

import hashlib
from importlib.resources import files

from powerforge_provenance.spatial_base import POLICY, identity_hash


def spatial_contract_identity():
    root = files("powerforge_provenance")
    names = (
        "spatial_base.py",
        "spatial_geometry.py",
        "spatial_sources.py",
        "spatial_offsets.py",
        "spatial_layout.py",
        "spatial_identity.py",
        "resources/spatial_v1.json",
    )
    return {
        "version": POLICY["version"],
        "rules_hash": identity_hash(
            {name: hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest() for name in names}
        ),
        "policy_sha256": identity_hash(dict(POLICY)),
    }
