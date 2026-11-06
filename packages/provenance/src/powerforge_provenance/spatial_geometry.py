"""Exact orthogonal crop/scale/mirror/quarter-turn transforms, not layout inference."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Literal

from pydantic import Field, field_validator, model_validator

from powerforge_provenance.spatial_base import POLICY, ExactDecimal, SpatialContract, revalidate


class Rectangle(SpatialContract):
    x: ExactDecimal = Field(ge=-1_000_000_000, le=1_000_000_000)
    y: ExactDecimal = Field(ge=-1_000_000_000, le=1_000_000_000)
    width: ExactDecimal = Field(gt=0, le=1_000_000_000)
    height: ExactDecimal = Field(gt=0, le=1_000_000_000)

    @property
    def right(self):
        with localcontext() as ctx:
            ctx.prec = 50
            return self.x + self.width

    @property
    def bottom(self):
        with localcontext() as ctx:
            ctx.prec = 50
            return self.y + self.height


class CoordinateFrame(SpatialContract):
    unit: Literal["PDF_POINTS", "PIXELS"]
    width: ExactDecimal = Field(gt=0, le=1_000_000_000)
    height: ExactDecimal = Field(gt=0, le=1_000_000_000)
    origin_x: ExactDecimal = Field(default=Decimal(0), ge=-1_000_000_000, le=1_000_000_000)
    origin_y: ExactDecimal = Field(default=Decimal(0), ge=-1_000_000_000, le=1_000_000_000)

    @property
    def bounds(self):
        return Rectangle(x=self.origin_x, y=self.origin_y, width=self.width, height=self.height)


class NormalizedRegion(Rectangle):
    x: ExactDecimal = Field(ge=0, le=1)
    y: ExactDecimal = Field(ge=0, le=1)
    width: ExactDecimal = Field(gt=0, le=1)
    height: ExactDecimal = Field(gt=0, le=1)

    @model_validator(mode="after")
    def within_page(self):
        if self.right > 1 or self.bottom > 1:
            raise ValueError("Region is outside the upright page")
        return self


class Point(SpatialContract):
    x: ExactDecimal = Field(ge=-1_000_000_000, le=1_000_000_000)
    y: ExactDecimal = Field(ge=-1_000_000_000, le=1_000_000_000)


class NormalizedPoint(Point):
    x: ExactDecimal = Field(ge=0, le=1)
    y: ExactDecimal = Field(ge=0, le=1)


def convex_quad(points: tuple[Point, ...]):
    """Four perimeter-ordered vertices; reject crossed or collapsed geometry."""
    if len(points) != 4 or len({(p.x, p.y) for p in points}) != 4:
        return False
    with localcontext() as ctx:
        ctx.prec = 50
        cross = []
        for i in range(4):
            a, b, c = points[i], points[(i + 1) % 4], points[(i + 2) % 4]
            cross.append((b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x))
        return all(v > 0 for v in cross) or all(v < 0 for v in cross)


def contained(inner: Rectangle, outer: Rectangle):
    return (
        outer.x <= inner.x
        and outer.y <= inner.y
        and inner.right <= outer.right
        and inner.bottom <= outer.bottom
    )


def normalize_rectangle(rectangle: Rectangle, frame: CoordinateFrame):
    rectangle, frame = revalidate(rectangle), revalidate(frame)
    if not contained(rectangle, frame.bounds):
        raise ValueError("Source rectangle is outside its declared frame")
    quantum = Decimal(1).scaleb(-POLICY["coordinate_decimal_places"])
    with localcontext() as ctx:
        ctx.prec = 50
        left = ((rectangle.x - frame.origin_x) / frame.width).quantize(quantum, ROUND_HALF_EVEN)
        top = ((rectangle.y - frame.origin_y) / frame.height).quantize(quantum, ROUND_HALF_EVEN)
        right = ((rectangle.right - frame.origin_x) / frame.width).quantize(
            quantum, ROUND_HALF_EVEN
        )
        bottom = ((rectangle.bottom - frame.origin_y) / frame.height).quantize(
            quantum, ROUND_HALF_EVEN
        )
        return NormalizedRegion(x=left, y=top, width=right - left, height=bottom - top)


class UprightTransform(SpatialContract):
    version: Literal["upright-orthogonal-transform-v1"] = "upright-orthogonal-transform-v1"
    source_frame: CoordinateFrame
    target_frame: CoordinateFrame
    # These rectangles explicitly describe crop/content padding and page placement.
    source_region: Rectangle
    target_region: Rectangle
    rotation_degrees: Literal[0, 90, 180, 270] = 0
    mirror_x: bool = False
    mirror_y: bool = False

    @field_validator("rotation_degrees", mode="before")
    @classmethod
    def integer_rotation(cls, value):
        if type(value) is not int:
            raise ValueError("Rotation must be an integer quarter turn")
        return value

    @model_validator(mode="after")
    def regions_fit(self):
        if not contained(self.source_region, self.source_frame.bounds) or not contained(
            self.target_region, self.target_frame.bounds
        ):
            raise ValueError("Transform regions must fit their immutable frames")
        return self

    def map_rectangle(self, rectangle: Rectangle):
        transform, rectangle = revalidate(self), revalidate(rectangle)
        if not contained(rectangle, transform.source_region):
            raise ValueError("Source box is outside the supported content/crop region")
        points = [
            transform.map_point(Point(x=x, y=y))
            for x in (rectangle.x, rectangle.right)
            for y in (rectangle.y, rectangle.bottom)
        ]
        return region_for_points(tuple(points))

    def map_point(self, point: Point):
        transform, point = revalidate(self), revalidate(point)
        source = transform.source_region
        if not source.x <= point.x <= source.right or not source.y <= point.y <= source.bottom:
            raise ValueError("Point is outside the supported content/crop region")
        with localcontext() as ctx:
            ctx.prec = 50
            u, v = (point.x - source.x) / source.width, (point.y - source.y) / source.height
            u, v = (1 - u if transform.mirror_x else u), (1 - v if transform.mirror_y else v)
            if transform.rotation_degrees == 90:
                u, v = 1 - v, u
            elif transform.rotation_degrees == 180:
                u, v = 1 - u, 1 - v
            elif transform.rotation_degrees == 270:
                u, v = v, 1 - u
            x = transform.target_region.x + u * transform.target_region.width
            y = transform.target_region.y + v * transform.target_region.height
            frame = transform.target_frame
            quantum = Decimal(1).scaleb(-POLICY["coordinate_decimal_places"])
            return NormalizedPoint(
                x=((x - frame.origin_x) / frame.width).quantize(quantum, ROUND_HALF_EVEN),
                y=((y - frame.origin_y) / frame.height).quantize(quantum, ROUND_HALF_EVEN),
            )


def region_for_points(points: tuple[NormalizedPoint, ...]):
    if not points or len(points) > 4 * POLICY["max_support_refs"]:
        raise ValueError("A region requires bounded nonempty point support")
    points = tuple(revalidate(p) for p in points)
    with localcontext() as ctx:
        ctx.prec = 50
        left, top = min(p.x for p in points), min(p.y for p in points)
        return NormalizedRegion(
            x=left,
            y=top,
            width=max(p.x for p in points) - left,
            height=max(p.y for p in points) - top,
        )


def union_regions(regions: tuple[NormalizedRegion, ...]):
    """Caller must first establish shared page/frame and exact support membership."""
    if not regions or len(regions) > POLICY["max_support_refs"]:
        raise ValueError("A region union needs bounded nonempty support")
    regions = tuple(revalidate(r) for r in regions)
    with localcontext() as ctx:
        ctx.prec = 50
        left, top = min(r.x for r in regions), min(r.y for r in regions)
        return NormalizedRegion(
            x=left,
            y=top,
            width=max(r.right for r in regions) - left,
            height=max(r.bottom for r in regions) - top,
        )
