"""The standard grooving tool: a blade with a rounded front on a holder, outside or inside, right or left hand.

Everything is first drawn for a right-hand OUTSIDE tool in blade coordinates (u: from the tip along the blade, z: across
it), then turned into the real coordinates:

- the blade is `blade_width_mm` wide (across Z) and `reach_mm` long (from the tip). Its two sides and its front are
  cutting edges. The front is a straight line between two corners rounded with `corner_radius_mm`. The front angle is
  the angle inside the blade at the left corner (the one with the smaller Z) between the left side and the front: 90 is
  square, above 90 the right corner is deeper, below 90 the left corner is deeper.
- the holder is a rectangle behind the blade, flush with the left side of the blade. Outside, its length runs along X
  from the tip to the furthest point and its width across Z. Inside, the tool is turned the other way (the blade points
  outward, the body lies towards the axis) and the two swap: the length runs along Z from the left side of the blade to
  the furthest point (a bar, like a boring bar) and the width along X.
- a left-hand tool is the mirror image in Z (outside) or in X (inside: it is the tool on the other side of the axis, cutting
  the far wall of the bore with the spindle reversed).

The outline has the deepest point of the front at x = 0. The touch-off point is the named point `tip`: Z is the side
face of the chosen corner, X is the point that touches first. It may lie in the air for a slanted front.
"""

from __future__ import annotations

import math

from ..constants import (
    GEOMETRY_TOLERANCE_MM,
    GROOVE_TOOL_FRONT_ANGLE_MAX_DEG,
    GROOVE_TOOL_FRONT_ANGLE_MIN_DEG,
    HALF,
    TIP_POINT,
    TOOL_SHAPE_DECIMALS,
)
from ..contour import NamedPoint
from ..geometry import LineSegment, Point
from .tool import Tool, ToolError, ToolSegment, ToolSegmentRole, ToolShape
from .tool_reference import arc_extremes
from .turning_tool_shape import nose_arc

Pair = tuple[float, float]  # (u, z) in blade coordinates


def groove_tool_shape(
    corner_radius_mm: float, front_angle_deg: float, blade_width_mm: float, reach_mm: float,
    holder_width_mm: float, holder_length_mm: float, inside: bool,
) -> tuple[list[tuple[Pair, Pair, Pair | None, ToolSegmentRole]], float]:
    """The outline of a right-hand tool in blade coordinates with the deepest point of the front at u = 0.

    Returns the pieces (start, end, arc centre or None, role), the blade end `u` and the middle of the end of the holder.
    Raises ToolError for dimensions that do not make a tool.
    """
    if min(blade_width_mm, reach_mm, holder_width_mm, holder_length_mm) <= 0 or corner_radius_mm < 0:
        raise ToolError("a grooving tool needs a positive blade width, reach and holder size, and a corner radius of 0 or more")
    if not GROOVE_TOOL_FRONT_ANGLE_MIN_DEG <= front_angle_deg <= GROOVE_TOOL_FRONT_ANGLE_MAX_DEG:
        raise ToolError(f"the front angle must be between {GROOVE_TOOL_FRONT_ANGLE_MIN_DEG} and {GROOVE_TOOL_FRONT_ANGLE_MAX_DEG} degrees")
    alpha = math.radians(front_angle_deg)
    width, radius = blade_width_mm, corner_radius_mm
    left_reach, right_reach = radius / math.tan(alpha * HALF), radius * math.tan(alpha * HALF)  # corner to where the rounding touches
    if left_reach + right_reach >= width / math.sin(alpha) - GEOMETRY_TOLERANCE_MM and radius > 0:
        raise ToolError("the corner radius is too big for the blade width")
    cos, sin = math.cos(alpha), math.sin(alpha)
    left, right = (0.0, 0.0), (width / math.tan(alpha), width)  # the sharp corners of the front
    left_face, left_front = (left[0] + left_reach, 0.0), (left[0] + left_reach * cos, left_reach * sin)
    right_front, right_face = (right[0] - right_reach * cos, right[1] - right_reach * sin), (right[0] + right_reach, width)
    centres = ((left_face[0], radius), (right_face[0], width - radius))
    lowest = [left_face[0], right_face[0], left_front[0], right_front[0]]
    if radius > 0:
        for start, end, centre in ((left_face, left_front, centres[0]), (right_front, right_face, centres[1])):
            lowest += [point.x for point in arc_extremes(nose_arc((start, end, centre)))]
    deepest = min(lowest)
    blade_end = deepest + reach_mm
    if blade_end <= max(left_face[0], right_face[0], left_front[0], right_front[0]) + GEOMETRY_TOLERANCE_MM:
        raise ToolError("the blade is too short for its front")
    if inside:
        holder_u, holder_z = blade_end + holder_width_mm, holder_length_mm
    else:
        holder_u, holder_z = deepest + holder_length_mm, holder_width_mm
    if holder_z < width - GEOMETRY_TOLERANCE_MM:
        raise ToolError("the holder is narrower than the blade" if not inside else "the holder is shorter than the blade is wide")
    if holder_u <= blade_end + GEOMETRY_TOLERANCE_MM:
        raise ToolError("the holder does not reach behind the blade: make its length bigger than the reach" if not inside else "the holder needs a width")
    cutter, holder = ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER
    top = (blade_end, width)
    items: list[tuple[Pair, Pair, Pair | None, ToolSegmentRole]] = []
    if radius > 0:
        items.append((left_face, left_front, centres[0], cutter))
    items.append((left_front, right_front, None, cutter))
    if radius > 0:
        items.append((right_front, right_face, centres[1], cutter))
    items += [
        (right_face, top, None, cutter), (top, (blade_end, holder_z), None, holder), ((blade_end, holder_z), (holder_u, holder_z), None, holder),
        ((holder_u, holder_z), (holder_u, 0.0), None, holder), ((holder_u, 0.0), (blade_end, 0.0), None, holder), ((blade_end, 0.0), left_face, None, cutter),
    ]

    def shifted(pair: Pair) -> Pair:
        return (pair[0] - deepest, pair[1])

    pieces = [
        (shifted(start), shifted(end), None if centre is None else shifted(centre), role)
        for start, end, centre, role in items if centre is not None or math.dist(start, end) > GEOMETRY_TOLERANCE_MM
    ]
    return pieces, blade_end - deepest


def groove_tool(
    number: int, name: str, left_hand: bool, inside: bool, corner_right: bool, corner_radius_mm: float, front_angle_deg: float,
    blade_width_mm: float, reach_mm: float, holder_width_mm: float, holder_length_mm: float,
) -> Tool:
    """The grooving tool. `corner_right`: the touch-off point is at the corner with the larger Z (else the smaller Z)."""
    pieces, _blade_end = groove_tool_shape(
        corner_radius_mm, front_angle_deg, blade_width_mm, reach_mm, holder_width_mm, holder_length_mm, inside,
    )
    # Inside the blade points outward (the body towards the axis) for the right hand. The left hand is the mirror image in Z
    # outside and in X inside (it works on the far wall of the bore).
    side = -1 if inside and not left_hand else 1
    hand = -1 if left_hand and not inside else 1

    def put(pair: Pair) -> Point:
        return Point(round(side * pair[0], TOOL_SHAPE_DECIMALS) + 0.0, round(hand * pair[1], TOOL_SHAPE_DECIMALS) + 0.0)

    segments: list[ToolSegment] = []
    for start, end, centre, role in pieces:
        if centre is None:
            segments.append(ToolSegment(LineSegment(put(start), put(end)), role))
        else:
            points = [put(start), put(end), put(centre)]
            segments.append(ToolSegment(nose_arc(tuple((p.x, p.z) for p in points)), role))
    faces = sorted((0.0, hand * blade_width_mm))  # the Z of the two side faces: the smaller one is the left corner
    tip_z = faces[1] if corner_right else faces[0]
    points = (NamedPoint(TIP_POINT, 0.0, tip_z),)
    return Tool(number, name, ToolShape(tuple(segments)), points=points)
