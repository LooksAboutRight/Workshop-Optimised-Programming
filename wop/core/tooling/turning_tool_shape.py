"""The standard turning tool: a bar with two cutting edges at the tip, drawn from a few dimensions.

Seen from the side of the work (x = radius, z = axial), a right-hand tool has its body towards larger Z and larger X
and cuts towards the chuck (smaller Z). The tip has two edges:

- the side edge faces the chuck. Its angle is measured to the feed direction (towards the chuck), as in a holder
  catalogue (93, 95 ...): 90 degrees is a plain edge along X, more than 90 leans back (clearance), less than 90 leans
  forward over the work.
- the front edge faces the axis. Its angle is measured to the facing direction (towards the axis) in the same way. It
  runs until the far side of the tool, so its length follows from the width.

The side edge is a cutting edge until it is `edge_length_mm` further out in X than the nose (the front edge ends the same way, `width_mm` along Z from the tip). Where it ends the tool steps back: a line
at a right angle to the edge returns to the near side of the body, as on a hand-ground tool. With an edge angle of 90
degrees or less there is no step. The corner is rounded with the nose radius. A left-hand tool is the mirror image in Z.
The outline is moved so that the box around the cutting edges has its corner at the origin; the touch-off point of
`tool_reference` is that corner, or the point under the nose when the side edge leans forward.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..constants import (
    GEOMETRY_TOLERANCE_MM,
    HALF,
    TOOL_SHAPE_DECIMALS,
    TURNING_TOOL_ANGLE_MAX_DEG,
    TURNING_TOOL_ANGLE_MIN_DEG,
    TURNING_TOOL_MIN_TIP_DEG,
    TURNING_TOOL_STEP_EPSILON_MM,
)
from ..geometry import ArcDirection, ArcSegment, LineSegment, Point
from .tool import Tool, ToolError, ToolSegment, ToolSegmentRole, ToolShape
from .tool_reference import arc_extremes

Pair = tuple[float, float]  # (x, z)


@dataclass(frozen=True)
class TurningToolShape:
    """The outline of a right-hand turning tool with the sharp corner at the origin (not yet moved, no hand applied)."""

    tip_angle_deg: float
    front_edge_length_mm: float  # from the sharp corner to the far side of the tool
    lines: tuple[tuple[Pair, Pair, ToolSegmentRole], ...]  # the straight pieces in order, after the nose arc
    arc: tuple[Pair, Pair, Pair] | None  # start, end and centre of the nose arc, None for a sharp tool
    corner: Pair  # the corner of the box round the cutting edges: the touch-off point


def turning_tool_shape(
    nose_radius_mm: float, side_angle_deg: float, front_angle_deg: float, edge_length_mm: float, width_mm: float, length_mm: float,
    body_offset_mm: float = 0,
) -> TurningToolShape:
    """Work out the outline. Raises ToolError for dimensions that do not make a tool.

    `body_offset_mm` moves the near side of the body away from the tip in Z (0: the body starts at the tip). The boring bar
    uses it: its head stands out of the bar by that much, and the side edge ends where it meets the body."""
    if min(width_mm, length_mm, edge_length_mm) <= 0 or nose_radius_mm < 0 or not 0 <= body_offset_mm < width_mm:
        raise ToolError("a turning tool needs a positive width, length and cutting edge length, and a nose radius of 0 or more")
    for angle in (side_angle_deg, front_angle_deg):
        if not TURNING_TOOL_ANGLE_MIN_DEG <= angle <= TURNING_TOOL_ANGLE_MAX_DEG:
            raise ToolError(f"the edge angles must be between {TURNING_TOOL_ANGLE_MIN_DEG} and {TURNING_TOOL_ANGLE_MAX_DEG} degrees")
    a, b = math.radians(side_angle_deg), math.radians(front_angle_deg)
    to_side, to_front = (math.sin(a), -math.cos(a)), (-math.cos(b), math.sin(b))  # unit directions of the edges from the sharp corner
    cross = to_side[0] * to_front[1] - to_side[1] * to_front[0]
    tip = math.atan2(cross, to_side[0] * to_front[0] + to_side[1] * to_front[1])
    if cross <= 0 or math.degrees(tip) < TURNING_TOOL_MIN_TIP_DEG:
        raise ToolError("the two edge angles leave no tip: lower one of them")
    reach = nose_radius_mm / math.tan(tip * HALF)  # from the sharp corner to where the nose arc touches an edge
    side_start, front_start = (reach * to_side[0], reach * to_side[1]), (reach * to_front[0], reach * to_front[1])
    arc = None
    xs, zs = [side_start[0], front_start[0]], [side_start[1], front_start[1]]
    if nose_radius_mm > 0:
        bisector = (to_side[0] + to_front[0], to_side[1] + to_front[1])
        scale = nose_radius_mm / math.sin(tip * HALF) / math.hypot(*bisector)
        centre = (bisector[0] * scale, bisector[1] * scale)
        arc = (front_start, side_start, centre)
        for point in arc_extremes(nose_arc(arc)):
            xs.append(point.x)
            zs.append(point.z)
    side_reach = (min(xs) + edge_length_mm) / to_side[0]  # the side edge ends edge_length_mm further out in X than the nose
    if side_reach <= reach:
        raise ToolError("the nose radius is too big for the cutting edge length")
    if body_offset_mm > 0 and to_side[1] > 0:  # the edge leans towards the body: it ends where it meets it
        side_reach = min(side_reach, (min(zs) + body_offset_mm) / to_side[1])
        if side_reach <= reach:
            raise ToolError("the nose radius is too big for the head of the tool")
    side_end = (side_reach * to_side[0], side_reach * to_side[1])
    zs.append(side_end[1])
    near = min(zs)  # the near side of the body: the lowest Z of the cutting edges
    far = near + width_mm
    level = near + body_offset_mm  # where the near side of the body lies
    front_reach = far / to_front[1]
    front_end = (front_reach * to_front[0], far)
    if front_reach <= reach:
        raise ToolError("the tool is narrower than its nose")
    xs.append(front_end[0])
    bottom = min(xs)
    top = bottom + length_mm
    if side_end[1] >= far:
        raise ToolError("the side edge leans out of the width of the tool: make the tool wider or the edge shorter")
    drop = (side_end[1] - level) / math.sin(a)  # the step: at a right angle to the side edge, to the near side of the body
    step_end = (side_end[0] - drop * math.cos(a), level) if abs(drop) > TURNING_TOOL_STEP_EPSILON_MM else None
    side_of_front = lambda point: to_front[0] * point[1] - to_front[1] * point[0]  # which side of the front edge line a point is on
    if step_end is not None and side_of_front(step_end) * side_of_front((top, level)) <= 0:  # the step must stay on the body side of the front edge
        raise ToolError("the step behind the side edge would cut into the front edge: make the edge longer or the head smaller")
    if max(side_end[0], front_end[0], 0 if step_end is None else step_end[0]) > top + GEOMETRY_TOLERANCE_MM:
        raise ToolError("the tool is too short for its cutting edge and width")
    cutter, holder = ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER
    chain: list[tuple[Pair, ToolSegmentRole]] = [(side_start, cutter), (side_end, holder)]  # each point, with the role of the piece that starts there
    if step_end is not None:
        chain.append((step_end, holder))
    chain += [((top, level), holder), ((top, far), holder), (front_end, cutter), (front_start, cutter)]
    lines = tuple((p, q, role) for (p, role), (q, _next) in zip(chain, chain[1:]) if math.dist(p, q) > GEOMETRY_TOLERANCE_MM)
    return TurningToolShape(math.degrees(tip), math.hypot(*front_end), lines, arc, (bottom, near))


def nose_arc(arc: tuple[Pair, Pair, Pair]) -> ArcSegment:
    """The nose arc as a segment; it runs the short way from the front edge to the side edge."""
    start, end, centre = arc
    cross = (start[0] - centre[0]) * (end[1] - centre[1]) - (start[1] - centre[1]) * (end[0] - centre[0])
    return ArcSegment(Point(*start), Point(*end), Point(*centre), ArcDirection.CCW if cross > 0 else ArcDirection.CW)


def turning_tool(
    number: int, name: str, left_hand: bool, nose_radius_mm: float, side_angle_deg: float, front_angle_deg: float,
    edge_length_mm: float, width_mm: float, length_mm: float,
) -> Tool:
    """The turning tool with the tip at the origin; a left-hand tool is the right-hand one mirrored in Z."""
    shape = turning_tool_shape(nose_radius_mm, side_angle_deg, front_angle_deg, edge_length_mm, width_mm, length_mm)
    side = -1 if left_hand else 1
    origin_x, origin_z = shape.corner

    def put(pair: Pair) -> Point:
        return Point(round(pair[0] - origin_x, TOOL_SHAPE_DECIMALS) + 0.0, round(side * (pair[1] - origin_z), TOOL_SHAPE_DECIMALS) + 0.0)

    pieces: list[ToolSegment] = []
    if shape.arc is not None:
        arc = nose_arc(tuple((put(p).x, put(p).z) for p in shape.arc))
        pieces.append(ToolSegment(arc, ToolSegmentRole.CUTTER))
    pieces += [ToolSegment(LineSegment(put(p), put(q)), role) for p, q, role in shape.lines]
    return Tool(number, name, ToolShape(tuple(pieces)))
