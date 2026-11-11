"""The standard boring bar: a bar towards the axis with a head at the tip, drawn from a few dimensions.

It is the turning tool turned a quarter (`turning_tool_shape`): the bar lies along Z with its body towards smaller X, the
tip is at the highest X. Seen from above (x = radius, z = axial):

- the end edge faces the chuck and runs across the whole front of the head, `front_width_mm` from the tip. Its angle is
  measured to the feed direction (towards the chuck), as the side edge of the turning tool: 90 is square, more leans back.
- the wall edge faces the bore wall. Its angle is measured to the facing direction, away from the axis: 90 is parallel to
  the wall, more clears the wall (100: the edge leans away by 10 degrees). It cuts for `wall_edge_length_mm` along Z;
  where it meets the bar it ends, and a shorter edge steps (at a right angle) down to the bar.
- the bar is `bar_width_mm` wide (the full profile seen from above) and the head stands out by the rest of the front
  width, so that the bar clears the wall behind the head.

The right hand has its body towards smaller X (it works on the near wall of the bore). The left hand is the mirror image in X: its body
stands towards larger X from the tip and it works on the far wall of the bore (with the spindle reversed). It cuts towards the chuck. The
outline is moved so that the box round the cutting edges has its corner at the origin.
"""

from __future__ import annotations

from ..constants import TOOL_SHAPE_DECIMALS
from ..geometry import LineSegment, Point
from .tool import Tool, ToolError, ToolSegment, ToolSegmentRole, ToolShape
from .turning_tool_shape import Pair, TurningToolShape, nose_arc, turning_tool_shape


def boring_tool_shape(
    nose_radius_mm: float, end_angle_deg: float, wall_angle_deg: float, wall_edge_length_mm: float,
    front_width_mm: float, bar_width_mm: float, length_mm: float,
) -> TurningToolShape:
    """The outline in the frame of the turning tool (X along the bar, Z towards the axis): `boring_tool` turns it."""
    if bar_width_mm > front_width_mm:
        raise ToolError("the bar is wider than the front of the head")
    return turning_tool_shape(
        nose_radius_mm, wall_angle_deg, end_angle_deg, wall_edge_length_mm, front_width_mm, length_mm, front_width_mm - bar_width_mm,
    )


def boring_tool(
    number: int, name: str, nose_radius_mm: float, end_angle_deg: float, wall_angle_deg: float, wall_edge_length_mm: float,
    front_width_mm: float, bar_width_mm: float, length_mm: float, left_hand: bool = False,
) -> Tool:
    """The boring bar with the tip at the origin; the left hand is the mirror image in X."""
    shape = boring_tool_shape(nose_radius_mm, end_angle_deg, wall_angle_deg, wall_edge_length_mm, front_width_mm, bar_width_mm, length_mm)
    origin_x, origin_z = shape.corner
    side = 1 if left_hand else -1

    def put(pair: Pair) -> Point:  # a quarter turn: along the bar becomes Z, towards the axis becomes minus X (plus X for the left hand)
        return Point(round(side * (pair[1] - origin_z), TOOL_SHAPE_DECIMALS) + 0.0, round(pair[0] - origin_x, TOOL_SHAPE_DECIMALS) + 0.0)

    pieces: list[ToolSegment] = []
    if shape.arc is not None:
        pieces.append(ToolSegment(nose_arc(tuple((put(p).x, put(p).z) for p in shape.arc)), ToolSegmentRole.CUTTER))
    pieces += [ToolSegment(LineSegment(put(p), put(q)), role) for p, q, role in shape.lines]
    return Tool(number, name, ToolShape(tuple(pieces)))
