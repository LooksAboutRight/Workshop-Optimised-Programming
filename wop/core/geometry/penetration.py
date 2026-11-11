"""Which edges of a tool outline go into a region: the one test behind every reach and collision decision.

Every edge of the tool is cut where it crosses the border of the region (and where a corner of the border lies on it); every piece
is then tested with its middle and its ends: is it inside the region, further than the tolerance from its border? A piece that is
not only touches. A tool that lies completely inside a region, or a region that lies completely inside
the tool, has no crossing: a corner of each is tested too (the tool then penetrates with no edge to blame).

What the answer means depends on the region. Against the part and its allowance no edge may penetrate. Against the material that
stands, only edges that are not marked cutting may not: a cutting edge may be in material, it cuts there.
"""

from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass

from ..constants import GEOMETRY_TOLERANCE_MM, MIDPOINT_FRACTION
from .primitives import LineSegment, Point, Segment
from .intersect import fraction_along, intersections, point_of
from .distance import distance_to_segment
from .chains import INSIDE, ChainIndex, box_of, crossings, split_at
from .tool_edges import ToolLoop, placed

NO_EDGE = -1  # a penetration that no single edge is to blame for (a region completely inside the tool or the other way round)


@dataclass(frozen=True)
class Penetration:
    loop: int  # the tool loop (always 0: the tool)
    edge: int  # the edge in that loop, or NO_EDGE
    cutting: bool
    point: Point  # a place of the piece that lies inside the region


class RegionIndex(ChainIndex):
    """The border of a region with the box of every piece, made once and asked for every position of a tool."""

    def near_segment(self, segment: Segment, margin: float) -> list[Segment]:
        return self.near(box_of(segment), margin)


def _inside_place(index: RegionIndex, piece: Segment, tolerance: float) -> Point | None:
    """The first of the middle and the two ends of the piece that lies inside the region further than the tolerance from its border (`locate`
    calls a point inside only when no border piece is within the tolerance), None when none does."""
    for point in (point_of(piece, MIDPOINT_FRACTION), piece.start, piece.end):
        if index.locate(point, tolerance)[0] == INSIDE:
            return point
    return None


def penetrations(tool: Sequence[ToolLoop], region: RegionIndex, tip: Point, tolerance: float) -> list[Penetration]:
    """The pieces of the tool (its tip at `tip`) that go deeper into the region than `tolerance`."""
    return list(_penetrating(tool, region, tip, tolerance))


def _penetrating(tool: Sequence[ToolLoop], region: RegionIndex, tip: Point, tolerance: float):
    """`penetrations` one by one, so a yes-or-no question stops at the first one."""
    for number, loop in enumerate(placed(tool, tip)):
        for position, edge in enumerate(loop):
            if isinstance(edge.segment, LineSegment) and edge.segment.length <= GEOMETRY_TOLERANCE_MM:
                continue  # an edge of no length has nothing to test
            near = region.near_segment(edge.segment, tolerance)
            if not near:  # no border near the edge: it lies wholly inside or wholly outside, its middle says which
                middle = point_of(edge.segment, MIDPOINT_FRACTION)
                if region.locate(middle, tolerance)[0] == INSIDE:
                    yield Penetration(number, position, edge.cutting, middle)
                continue
            marks: list[float] = []
            for other in near:
                points = list(intersections(edge.segment, other))
                points += [p for p in (other.start, other.end) if distance_to_segment(p, edge.segment) <= tolerance]
                marks += [fraction_along(edge.segment, p) for p in points]
            for piece in split_at(edge.segment, marks):
                where = _inside_place(region, piece, tolerance)
                if where is not None:
                    yield Penetration(number, position, edge.cutting, where)
        # nothing crosses: the region may lie completely inside the tool
        outline = [edge.segment for edge in loop]
        for border in region.loops:
            corner = border[0].start
            if sum(1 for z in crossings([tuple(outline)], corner.x, 0) if z > corner.z) % 2 == 1 and not any(
                distance_to_segment(corner, segment) <= tolerance for segment in outline
            ):
                yield Penetration(number, NO_EDGE, False, corner)


def blocked_by_part(tool: Sequence[ToolLoop], region: RegionIndex, tip: Point, tolerance: float = GEOMETRY_TOLERANCE_MM) -> bool:
    """True when any edge of the tool penetrates the region (the part and its allowance): the position is not allowed."""
    return next(_penetrating(tool, region, tip, tolerance), None) is not None


def blocked_by_material(tool: Sequence[ToolLoop], region: RegionIndex, tip: Point, tolerance: float = GEOMETRY_TOLERANCE_MM) -> bool:
    """True when an edge that is not marked cutting penetrates the region (the material that stands): a collision."""
    return any(not p.cutting for p in _penetrating(tool, region, tip, tolerance))
