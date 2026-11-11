"""The path of the tool reference point that makes the rounded nose follow a contour (nose radius compensation made by WOP).

The reference point of a tool (`tool_reference`) sits rigidly on the nose circle, so the exact path of the reference
point is the contour moved to its free side by the nose radius (the path of the circle centre), then shifted by the
fixed vector from the centre to the reference point. On a cylinder or a face the result is the contour itself.

`path` stays the nominal contour. A later option that writes G41 / G42 for the controller uses the nominal contour and
leaves this offset out; nothing here changes what the contour or the block says.
"""

from __future__ import annotations

from .constants import GEOMETRY_TOLERANCE_MM
from .geometry.offset import offset_segments
from .geometry import ArcSegment, LineSegment, Segment
from .tooling.tool import Tool
from .tooling.tool_reference import nose_circle


def _shifted(segment: Segment, dx: float, dz: float) -> Segment:
    from .geometry import Point

    def move(point: Point) -> Point:
        return Point(point.x + dx, point.z + dz)

    if isinstance(segment, ArcSegment):
        return ArcSegment(move(segment.start), move(segment.end), move(segment.center), segment.direction)
    return LineSegment(move(segment.start), move(segment.end))


def reference_path(path: list[Segment], tool: Tool, free_side_up: bool, extra_mm: float = 0) -> list[tuple[int, Segment]]:
    """The path of the reference point of `tool` (tip at the origin) for a contour travelled from the tailstock
    towards the chuck. `free_side_up`: the free side of the contour (where the tool is) is towards larger X (outside
    turning), else towards smaller X (inside). Every piece comes with the index of the contour segment it belongs to.
    A tool without a nose radius gets the contour as it is. `extra_mm` moves the contour further to its free side first
    (the finishing allowance: the path of the roughing that leaves it)."""
    radius, centre = nose_circle(tool)
    tagged = list(enumerate(path))
    if radius <= GEOMETRY_TOLERANCE_MM and extra_mm <= GEOMETRY_TOLERANCE_MM:
        return tagged
    # Travelling towards the chuck (to the left in the picture), larger X is on the right hand: a negative distance
    # moves the pieces to the right (see geometry/offset.py), a positive one to the left.
    distance = radius + extra_mm
    pieces = offset_segments(tagged, -distance if free_side_up else distance, closed=False)
    if not pieces:
        return tagged
    return [(index, _shifted(segment, -centre.x, -centre.z)) for index, segment in pieces]
