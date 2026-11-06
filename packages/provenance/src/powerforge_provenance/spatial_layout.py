"""Spatial/binding shapes and support resolution, not an implementation of table admission."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from powerforge_provenance.spatial_base import (
    POLICY,
    SHA256,
    LocalRef,
    SpatialContract,
    bounded_json,
    identity_hash,
    revalidate,
)
from powerforge_provenance.spatial_geometry import (
    NormalizedPoint,
    NormalizedRegion,
    region_for_points,
)
from powerforge_provenance.spatial_sources import (
    PageOwner,
    PreparedPage,
    ProducerIdentity,
    load_positioned_text,
)


class EnrichmentResultRef(SpatialContract):
    id: UUID
    owner: PageOwner
    producer_run_id: UUID
    producer_work_unit_id: UUID
    producer_purpose: Literal["SOURCE_ENRICHMENT"] = "SOURCE_ENRICHMENT"
    result_kind: Literal["PREPARED", "SPATIAL"]
    manifest_sha256: SHA256
    producer_sha256: SHA256


class SourceSupport(SpatialContract):
    representation_ref: LocalRef
    kind: Literal["TOKEN", "NATIVE_PRIMITIVE"]
    ref: LocalRef


class SpatialRegion(SpatialContract):
    ref: LocalRef
    kind: Literal["CONTENT", "TABLE", "ROW", "COLUMN", "CELL", "HEADER", "CAPTION", "NOTE"]
    support: tuple[SourceSupport, ...] = Field(min_length=1, max_length=POLICY["max_support_refs"])
    region: NormalizedRegion | None

    @model_validator(mode="after")
    def distinct_support(self):
        if len(set(self.support)) != len(self.support):
            raise ValueError("Duplicate region support")
        return self


class SpatialRelation(SpatialContract):
    kind: Literal[
        "BEFORE",
        "CONTAINS",
        "HEADER_FOR",
        "SAME_ROW",
        "SAME_COLUMN",
        "ALIGNED_SAME_READING",
        "CONFLICTING_READING",
    ]
    left: LocalRef
    right: LocalRef
    # Server metadata vocabulary; accepting this shape is not proof of its assertion.
    basis: Literal[
        "NATIVE_GEOMETRY_SUPPORTED", "OCR_GEOMETRY_SUPPORTED", "VISUAL_REPORTED", "UNRESOLVED"
    ]


class SpatialPage(SpatialContract):
    version: Literal["spatial-source-page-v1"] = "spatial-source-page-v1"
    id: UUID
    owner: PageOwner
    producer_run_id: UUID
    producer_work_unit_id: UUID
    producer: ProducerIdentity
    prepared: EnrichmentResultRef
    regions: tuple[SpatialRegion, ...] = Field(max_length=POLICY["max_regions"])
    relations: tuple[SpatialRelation, ...] = Field(max_length=POLICY["max_relations"])

    @model_validator(mode="after")
    def graph_shape(self):
        if (
            self.prepared.result_kind != "PREPARED"
            or self.prepared.owner != self.owner
            or self.producer.kind != "SPATIAL_LAYOUT"
            or self.id == self.prepared.id
        ):
            raise ValueError("Spatial results require a separate owned preparation prerequisite")
        refs = {r.ref for r in self.regions}
        if len(refs) != len(self.regions) or len(set(self.relations)) != len(self.relations):
            raise ValueError("Duplicate spatial regions/relations")
        for relation in self.relations:
            if (
                relation.left not in refs
                or relation.right not in refs
                or relation.left == relation.right
            ):
                raise ValueError("Spatial relation has foreign/self endpoints")
        for kind in ("BEFORE", "CONTAINS", "HEADER_FOR"):
            graph = {ref: set() for ref in refs}
            for relation in self.relations:
                if relation.kind == kind:
                    graph[relation.left].add(relation.right)
            _acyclic(graph)
        bounded_json(self, POLICY["max_manifest_bytes"])
        return self

    @property
    def identity_hash(self):
        return identity_hash(self.model_dump(mode="json"))


def _acyclic(graph):
    while graph:
        leaves = {key for key, edges in graph.items() if not edges}
        if not leaves:
            raise ValueError("Cyclic spatial order/containment/header relationships")
        graph = {key: edges - leaves for key, edges in graph.items() if key not in leaves}


class SourceBinding(SpatialContract):
    version: Literal["enriched-page-binding-v1"] = "enriched-page-binding-v1"
    owner: PageOwner
    prepared: EnrichmentResultRef
    spatial: EnrichmentResultRef | None
    selected_representations: tuple[LocalRef, ...] = Field(max_length=POLICY["max_representations"])

    @model_validator(mode="after")
    def explicit_purposes(self):
        if self.prepared.owner != self.owner or self.prepared.result_kind != "PREPARED":
            raise ValueError("Binding requires an owned preparation result")
        if self.spatial is not None and (
            self.spatial.owner != self.owner
            or self.spatial.result_kind != "SPATIAL"
            or self.spatial.id == self.prepared.id
        ):
            raise ValueError("Binding requires a distinct owned spatial result")
        if len(set(self.selected_representations)) != len(self.selected_representations):
            raise ValueError("Duplicate selected source representations")
        return self

    @property
    def identity_hash(self):
        return identity_hash(self.model_dump(mode="json"))


def check_binding(binding: SourceBinding, prepared: PreparedPage, spatial: SpatialPage | None):
    """Detached identity consistency; actual completion/access checks remain mandatory."""
    binding, prepared = revalidate(binding), revalidate(prepared)
    p = binding.prepared
    if (
        prepared.owner != binding.owner
        or prepared.id != p.id
        or prepared.producer_run_id != p.producer_run_id
        or prepared.producer_work_unit_id != p.producer_work_unit_id
        or prepared.preparation_sha256 != p.producer_sha256
        or prepared.identity_hash != p.manifest_sha256
        or not set(binding.selected_representations) <= {r.ref for r in prepared.representations}
    ):
        raise ValueError("Binding differs from its exact prepared source snapshot")
    if binding.spatial is None:
        if spatial is not None:
            raise ValueError("Unselected spatial sources cannot enter a binding")
        return
    if spatial is None:
        raise ValueError("Selected spatial result is missing; no current-version fallback")
    spatial = revalidate(spatial)
    s = binding.spatial
    if (
        spatial.owner != binding.owner
        or spatial.id != s.id
        or spatial.prepared != p
        or spatial.identity_hash != s.manifest_sha256
        or spatial.producer.identity_hash != s.producer_sha256
        or spatial.producer_run_id != s.producer_run_id
        or spatial.producer_work_unit_id != s.producer_work_unit_id
    ):
        raise ValueError("Binding differs from its exact spatial source snapshot")


class GeometryResolution(SpatialContract):
    version: Literal["spatial-support-resolution-v1"] = "spatial-support-resolution-v1"
    owner: PageOwner
    support: tuple[SourceSupport, ...] = Field(min_length=1, max_length=POLICY["max_support_refs"])
    region: NormalizedRegion | None
    basis: Literal["PDF_NATIVE_GEOMETRY", "OCR_ENGINE_GEOMETRY", "MIXED_SOURCE_GEOMETRY", "NONE"]
    # No table/row ownership is established by a bounding-box union in M1.
    structure_basis: Literal["UNRESOLVED"] = "UNRESOLVED"
    printed_text_independently_verified: Literal[False] = False

    @field_validator("printed_text_independently_verified", mode="before")
    @classmethod
    def boolean_marker(cls, value):
        if type(value) is not bool:
            raise ValueError("Reading verification marker requires a boolean")
        return value

    @model_validator(mode="after")
    def unavailable(self):
        if (self.basis == "NONE") != (self.region is None):
            raise ValueError("Unsupported geometry must remain null")
        return self


def resolve_region_support(
    prepared: PreparedPage,
    region: SpatialRegion,
    geometry_bytes: dict[str, bytes],
    text_bytes: dict[str, bytes],
):
    prepared, region = revalidate(prepared), revalidate(region)
    representations, points, kinds, missing = {}, [], set(), False
    for support in region.support:
        alias = support.representation_ref
        if alias not in representations:
            if alias not in geometry_bytes or alias not in text_bytes:
                raise ValueError("Selected positioned source bytes are missing")
            representations[alias], _ = load_positioned_text(
                prepared, alias, geometry_bytes[alias], text_bytes[alias]
            )
        body = representations[alias]
        kinds.add(body.producer.kind)
        if support.kind == "TOKEN":
            token = next((t for t in body.tokens if t.ref == support.ref), None)
            if token is None:
                raise ValueError("Region cites a foreign source token")
            if token.source_box is None:
                missing = True
                continue
            if token.source_quad is not None:
                points.extend(body.transform.map_point(point) for point in token.source_quad)
                continue
            box = body.transform.map_rectangle(token.source_box)
            points.extend(
                (NormalizedPoint(x=box.x, y=box.y), NormalizedPoint(x=box.right, y=box.bottom))
            )
        else:
            primitive = next((p for p in body.native_primitives if p.ref == support.ref), None)
            if primitive is None:
                raise ValueError("Region cites unsupported native document geometry")
            points.extend(body.transform.map_point(p) for p in primitive.points)
    area_available = (
        bool(points) and len({p.x for p in points}) > 1 and len({p.y for p in points}) > 1
    )
    resolved = region_for_points(tuple(points)) if not missing and area_available else None
    if region.region is not None and region.region != resolved:
        raise ValueError("Declared region differs from its exact source support")
    return GeometryResolution(
        owner=prepared.owner,
        support=region.support,
        region=resolved,
        basis="NONE"
        if resolved is None
        else "MIXED_SOURCE_GEOMETRY"
        if len(kinds) > 1
        else "PDF_NATIVE_GEOMETRY"
        if kinds == {"NATIVE_PDF"}
        else "OCR_ENGINE_GEOMETRY",
    )
