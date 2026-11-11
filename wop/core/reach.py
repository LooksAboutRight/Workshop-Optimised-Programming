"""Reach and collision checks for a tool (stage S3b).

The tool shape is drawn in machine orientation (x = radius, z = axial) with
the tool tip at its origin. Placing the tool means moving that origin to a
tip position, nothing is rotated. So an outside tool has its body at larger x.

Rules:
- GOUGE: the tool must not cut into the finished part.
- HOLDER_IN_MATERIAL: the outline pieces tagged HOLDER
  must not enter the material that is still there. CUTTER pieces may.
- JAWS: the tool must not touch the jaws.
Touching is not collision (tolerance in constants.py).

The part is round, so its far side (x < 0) is the mirror of the near side. A tool body that reaches past
the axis (a boring bar in a small bore) is also tested, mirrored, against the near side: the mirrored tool
at the mirrored position meets the same material as the real tool meets on the far side. Only tools that
reach past the axis pay for this second test.

Positions along a path or a contour are tested at fixed steps; very thin
obstacles between two test positions can be missed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .constants import (
    ARC_MAX_DEVIATION_MM,
    DEFAULT_JAWS_EXTENT_MM,
    GEOMETRY_TOLERANCE_MM,
    MAX_SAMPLES_PER_SEGMENT,
)
from .geometry import Point, Segment, segments_to_polyline
from .program_model.raw_part import RawPart
from .geometry.region import Region
from .tooling.tool import Tool, ToolShape
from .lathe.workholding import Workholding, WorkholdingError, place_workholding


class CollisionKind(Enum):
    GOUGE = "gouge"
    HOLDER_IN_MATERIAL = "holder in material"
    JAWS = "jaws"


@dataclass(frozen=True)
class Collision:
    kind: CollisionKind
    message: str


@dataclass(frozen=True)
class CollisionContext:
    """What a tool can collide with."""

    protected: Region  # finished part plus finishing allowance: never cut into
    residual: Region  # material that is still there: holders must stay out
    jaws: Region | None = None


# --- setup -------------------------------------------------------------------


def jaws_region(raw_part: RawPart, jaws_outline: list[Segment] | None = None) -> Region:
    """The jaws: the user's outline if given, else a flat plane at the clamping position."""
    if jaws_outline:
        return Region.from_segments(jaws_outline)
    return Region.rectangle(
        0,
        raw_part.clamp_z_mm - DEFAULT_JAWS_EXTENT_MM,
        DEFAULT_JAWS_EXTENT_MM,
        raw_part.clamp_z_mm,
    )


def program_jaws(raw_part: RawPart, workholding: Workholding | None) -> tuple[Region, str]:
    """The surface the tool must not touch behind the work, and a problem text (empty if all is well).

    No workholding: the flat plane at the clamping position. Chuck and jaws are used as a ring (they turn with
    the spindle). If they cannot be placed on this raw part the flat plane is used and the problem says why.
    """
    if workholding is None or workholding.is_none:
        return jaws_region(raw_part), ""
    try:
        placed = place_workholding(raw_part, workholding)
    except WorkholdingError as error:
        return jaws_region(raw_part), f"workholding is not used: {error}; the flat clamping plane is checked instead"
    region: Region | None = None
    for outline in (placed.jaws, placed.chuck):
        if outline:
            part = Region.from_segments(list(outline))
            region = part if region is None else region.union(part)
    return (jaws_region(raw_part) if region is None else region), ""


def build_context(
    part: Region, residual: Region, jaws: Region | None = None, allowance_mm: float = 0
) -> CollisionContext:
    """allowance_mm keeps extra material on the part (finishing allowance)."""
    protected = part.offset(allowance_mm) if allowance_mm > 0 else part
    return CollisionContext(protected, residual, jaws)


# --- placing the tool ----------------------------------------------------------


def _shift(point: Point, tip: Point) -> Point:
    return Point(point.x + tip.x, point.z + tip.z)


def _placed_region(shape: ToolShape, tip: Point) -> Region:
    return Region.from_segments(shape.segments).translated(tip.x, tip.z)


def _placed_outline(segment: Segment, tip: Point) -> list[Point]:
    return [_shift(point, tip) for point in segments_to_polyline([segment], ARC_MAX_DEVIATION_MM)]


# --- checks --------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedTool:
    """Tool outlines built once, at the origin, for many position checks."""

    tool_number: int
    body: Region
    holder_outlines: tuple[tuple[Point, ...], ...]
    body_min_x: float = 0  # the lowest x of the body (tip at the origin)
    mirror: "PreparedTool | None" = None  # the tool turned over the axis; only for a body that reaches below x = 0


def prepare_tool(tool: Tool) -> PreparedTool:
    origin = Point(0, 0)
    body = _placed_region(tool.shape, origin)
    pieces = list(tool.shape.holder_segments)
    outlines = tuple(tuple(_placed_outline(piece, origin)) for piece in pieces)
    bounds = body.bounds
    lowest = 0 if bounds is None else bounds.min_x
    if lowest >= -GEOMETRY_TOLERANCE_MM:
        return PreparedTool(tool.number, body, outlines, lowest)
    turned = tuple(tuple(Point(-point.x, point.z) for point in outline) for outline in outlines)
    return PreparedTool(tool.number, body, outlines, lowest, PreparedTool(tool.number, body.mirrored(), turned))


def placed_shrunk(prepared: PreparedTool, tip: Point) -> Region:
    """The tool body as the collision checks compare it, with its tip at `tip`. The shrinking is done once (kept on the
    body's Region) and then only moved: this runs for every position of every move."""
    return prepared.body.shrunk_for_collision().translated(tip.x, tip.z)


def far_side_tip(prepared: PreparedTool, tip: Point) -> Point | None:
    """Where the mirrored tool stands when the real tool at `tip` reaches past the axis, else None."""
    if prepared.mirror is None or tip.x + prepared.body_min_x >= -GEOMETRY_TOLERANCE_MM:
        return None
    return Point(-tip.x, tip.z)


def axis_gap(prepared: PreparedTool, tip: Point) -> float:
    """How far (mm, roughly) the tip can still move before the tool starts to reach past the axis; infinite for a
    tool that never does. For a tool that reaches past already: 0."""
    if prepared.mirror is None:
        return math.inf
    return max(tip.x + prepared.body_min_x, 0)


def check_prepared(
    prepared: PreparedTool, tip: Point, context: CollisionContext, body: Region | None = None, holder: bool = True
) -> list[Collision]:
    """`body`: the result of `placed_shrunk` when the caller has it already. `holder`: False leaves out the test of
    the holder in the material (rapid moves do not need it). A tool that reaches past the axis is tested on the
    far side too (the mirrored tool against the near side)."""
    found = _collisions(prepared, tip, context, body, holder)
    far = far_side_tip(prepared, tip)
    if far is not None:
        seen = {collision.kind for collision in found}
        for collision in _collisions(prepared.mirror, far, context, None, holder):
            if collision.kind not in seen:
                found.append(Collision(collision.kind, f"{collision.message} (on the far side of the axis)"))
    return found


def _collisions(
    prepared: PreparedTool, tip: Point, context: CollisionContext, body: Region | None, holder: bool
) -> list[Collision]:
    if body is None:
        body = placed_shrunk(prepared, tip)
    number = prepared.tool_number
    collisions: list[Collision] = []
    if not body.is_empty and body.overlaps(context.protected.shrunk_for_collision()):
        collisions.append(
            Collision(CollisionKind.GOUGE, f"tool T{number} cuts into the finished part")
        )
    for outline in prepared.holder_outlines if holder else ():
        placed = [_shift(point, tip) for point in outline]
        if context.residual.length_inside(placed) > 0:
            collisions.append(
                Collision(
                    CollisionKind.HOLDER_IN_MATERIAL,
                    f"holder of tool T{number} runs into the material",
                )
            )
            break
    if context.jaws is not None and not body.is_empty and body.overlaps(context.jaws.shrunk_for_collision()):
        collisions.append(Collision(CollisionKind.JAWS, f"tool T{number} touches the jaws"))
    return collisions


def check_position(tool: Tool, tip: Point, context: CollisionContext) -> list[Collision]:
    """All collisions of the tool with its tip at the given position."""
    return check_prepared(prepare_tool(tool), tip, context)


def sample_segments(segments: list[Segment], step_mm: float) -> list[Point]:
    """Points along a chain of segments, at most step_mm apart, ends included. Raises ValueError for a piece so long
    that testing it would take minutes (a value typed with too many digits)."""
    points: list[Point] = []
    for segment in segments:
        count = max(1, math.ceil(segment.length / step_mm))
        if count > MAX_SAMPLES_PER_SEGMENT:
            raise ValueError(
                f"a move of {segment.length:g} mm would need {count} check positions at a step of {step_mm:g} mm "
                f"(the limit is {MAX_SAMPLES_PER_SEGMENT}): check the values, or raise the path check step in File > Preferences"
            )
        first = 0 if not points else 1
        points.extend(segment.point_at(index / count) for index in range(first, count + 1))
    return points
