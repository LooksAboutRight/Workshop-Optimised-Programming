"""The tool as closed loops of edges that are marked cutting or not.

A tool outline is a closed chain of pieces; each piece is a cutting edge or a holder edge. Only cutting edges may be in material; that
rule is applied in `penetration.py`. The loops are made from a tool in `analytic/tool_outline.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass

from ..constants import GEOMETRY_TOLERANCE_MM
from .chains import closed_loop, loop_area
from .offset import offset_segments
from .primitives import ArcSegment, LineSegment, Point, Segment


@dataclass(frozen=True)
class ToolEdge:
    segment: Segment
    cutting: bool


ToolLoop = Sequence[ToolEdge]  # a tuple or a list


def translated(point: Point, dx: float, dz: float) -> Point:
    return Point(point.x + dx, point.z + dz)


def translated_segment(segment: Segment, dx: float, dz: float) -> Segment:
    if isinstance(segment, LineSegment):
        return LineSegment(translated(segment.start, dx, dz), translated(segment.end, dx, dz))
    return ArcSegment(translated(segment.start, dx, dz), translated(segment.end, dx, dz), translated(segment.center, dx, dz), segment.direction)


def grown_loops(loops: Sequence[ToolLoop], distance: float) -> list[ToolLoop]:
    """The loops moved outwards by `distance` (the corners rounded), every edge marked not cutting: the room a tool keeps from the material on
    a rapid (the clearance of the project)."""
    grown: list[ToolLoop] = []
    for loop in loops:
        segments = [edge.segment for edge in loop if not (isinstance(edge.segment, LineSegment) and edge.segment.length <= GEOMETRY_TOLERANCE_MM)]
        counter_clockwise = loop_area(tuple(segments)) > 0
        moved = [segment for _index, segment in offset_segments(list(enumerate(segments)), distance if counter_clockwise else -distance, closed=True)]
        grown.append(tuple(ToolEdge(segment, False) for segment in closed_loop(moved)))
    return grown


def placed(loops: Sequence[ToolLoop], tip: Point) -> list[ToolLoop]:
    """The loops with the tool tip (the origin of the tool) at `tip`."""
    return [tuple(ToolEdge(translated_segment(edge.segment, tip.x, tip.z), edge.cutting) for edge in loop) for loop in loops]


