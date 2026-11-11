"""Regions as closed chains of lines and arcs, and the trim-and-link boolean on them.

A region is a list of closed loops. An outer loop runs counter-clockwise in the (x, z) plane, a hole clockwise, so the
inside is always on the left of the direction of travel. The boolean works like a trim in a drawing program:
  1. every piece of both chains is cut at the places where it crosses or touches the other chain (and where a vertex of
     the other chain lies on it),
  2. every piece is tested with its middle point against the other chain: inside, outside or on it,
  3. the pieces that belong to the result are kept (the ones on the other chain only when the two regions lie on the
     same side or on opposite sides, as the operation needs),
  4. the kept pieces are joined end to end into loops.
Arcs stay arcs. Only the test "is this point inside" uses chords of the arcs, and only for points that are not near
the boundary. Nothing here knows a tool, a block or a program.
"""

from __future__ import annotations

from collections.abc import Sequence

import math

from ..constants import CHAIN_TOLERANCE_RETRIES, CONTACT_SEARCH_STEPS, GEOMETRY_TOLERANCE_MM, MIDPOINT_FRACTION
from .primitives import ArcDirection, ArcSegment, LineSegment, Point, Segment
from .intersect import fraction_along, intersections, point_of
from .distance import distance_to_segment
from .chain_index import (  # noqa: F401  (the boxes, the index and the crossings were here first: the other modules import them from here)
    INSIDE, ON, OUTSIDE, Box, ChainIndex, Loop, box_of, boxes_meet, coordinates, crossing_value, crossings, loops_box, monotone, split_at,
)

INTERSECTION = "intersection"
DIFFERENCE = "difference"


class ChainError(ValueError):
    """The chains cannot be joined into closed loops."""


# --- building loops -----------------------------------------------------------------------------

def reversed_segment(segment: Segment) -> Segment:
    if isinstance(segment, LineSegment):
        return LineSegment(segment.end, segment.start)
    flipped = ArcDirection.CW if segment.direction is ArcDirection.CCW else ArcDirection.CCW
    return ArcSegment(segment.end, segment.start, segment.center, flipped)


def reversed_loop(loop: Loop) -> Loop:
    return tuple(reversed_segment(segment) for segment in reversed(loop))


def loop_area(loop: Loop) -> float:
    """Signed area of a loop (positive: counter-clockwise), exact: the area of the polygon of the ends plus the circular segment of every arc."""
    total = 0.0
    for segment in loop:
        total += (segment.start.x * segment.end.z - segment.end.x * segment.start.z) / 2
        if isinstance(segment, ArcSegment):
            first = segment.start_angle
            last = first + segment.turn * segment.sweep
            centre = segment.center
            radius = segment.radius
            # the integral of (x dz - z dx) / 2 along the arc, less the straight chord already counted above
            along = radius * radius * (last - first) + radius * (
                centre.x * (math.sin(last) - math.sin(first)) - centre.z * (math.cos(last) - math.cos(first))
            )
            total += along / 2 - (segment.start.x * segment.end.z - segment.end.x * segment.start.z) / 2
    return total


def oriented(loop: Loop, counter_clockwise: bool = True) -> Loop:
    return loop if (loop_area(loop) > 0) == counter_clockwise else reversed_loop(loop)


def polygon_loop(points: Sequence[Point] | tuple[Point, ...]) -> Loop:
    """The loop of a polygon given by its corners (a repeated first corner at the end is allowed)."""
    corners = list(points)
    if len(corners) > 1 and corners[0].is_close(corners[-1]):
        corners = corners[:-1]
    return tuple(LineSegment(a, b) for a, b in zip(corners, corners[1:] + corners[:1]) if not a.is_close(b))


def closed_loop(segments: Sequence[Segment]) -> Loop:
    """A loop from pieces that already follow each other; the last piece must end where the first starts."""
    if not segments[-1].end.is_close(segments[0].start):
        raise ChainError("the pieces do not close")
    return tuple(segments)


def loops_of_region(region) -> list[Loop]:
    """The loops of a region (`Region`), arcs and all: outer boundaries counter-clockwise, holes clockwise."""
    return list(region.loops)


def region_of_loops(loops: Sequence[Loop]):
    """A `Region` of the loops: for pictures and for comparing in tests. The loops may overlap: they are added one at a time (a
    clockwise one is taken away)."""
    from .region import Region  # late: the region module is built on this one

    region = Region.empty()
    for loop in loops:
        if loop:
            piece = Region.from_loops([oriented(loop, True)])
            region = region.difference(piece) if loop_area(loop) < 0 else region.union(piece)
    return region


# --- cutting pieces ------------------------------------------------------------------------------

def _cut(segment: Segment, others: Sequence[Segment], tolerance: float) -> list[Segment]:
    """The piece cut at every place where it crosses or touches another piece, or where an end of another piece lies on it
    (within `tolerance`)."""
    marks: list[float] = []
    for other in others:
        points = list(intersections(segment, other))
        points += [p for p in (other.start, other.end) if distance_to_segment(p, segment) <= tolerance]
        marks += [fraction_along(segment, p) for p in points]
    return split_at(segment, marks)


# --- where a point is ---------------------------------------------------------------------------

def _inside(point: Point, loops: Sequence[Loop]) -> bool:
    """Even-odd test with a ray towards larger z, exact on arcs (the ray is a line at constant radius)."""
    return sum(1 for z in crossings(loops, point.x, 0) if z > point.z) % 2 == 1


def _tangent(segment: Segment, point: Point) -> tuple[float, float]:
    if isinstance(segment, LineSegment):
        dx, dz = segment.end.x - segment.start.x, segment.end.z - segment.start.z
    else:
        dx, dz = -(point.z - segment.center.z) * segment.turn, (point.x - segment.center.x) * segment.turn
    length = math.hypot(dx, dz)
    return dx / length, dz / length


def _same_way(piece: Segment, other: Segment | None, point: Point) -> bool:
    """True when `piece` runs the same way as `other` at `point` (a piece that lies on the border `other`: the two regions lie on the same
    side of it)."""
    assert other is not None  # `locate` names the piece the point lies on
    (ax, az), (bx, bz) = _tangent(piece, point), _tangent(other, point)
    return ax * bx + az * bz > 0


def locate(point: Point, loops: Sequence[Loop], tolerance: float) -> tuple[str, Segment | None]:
    """Inside, outside or on the loops (within `tolerance`); when on, the piece it lies on."""
    return ChainIndex(loops).locate(point, tolerance)


# --- the boolean -------------------------------------------------------------------------------

def _near_band(point: Point, others: Sequence[Segment], tolerance: float) -> bool:
    return any(distance_to_segment(point, other) <= tolerance for other in others)


def _homogeneous(piece: Segment, others: Sequence[Segment], tolerance: float, depth: int) -> list[Segment]:
    """The piece cut where it enters or leaves the band of `tolerance` around the other chain, when it is in the band in the middle
    but not at both ends: a piece that runs at a shallow angle to the other chain is 'on' it in the middle and off it at an end,
    and tested at its middle alone it would be called 'on' for its whole length. A piece that only starts in the band (at a
    crossing) is left alone."""
    if depth == 0 or piece.length <= tolerance:
        return [piece]
    if not _near_band(point_of(piece, MIDPOINT_FRACTION), others, tolerance):
        return [piece]  # the common case: the middle is off the other chain
    if _near_band(piece.start, others, tolerance) and _near_band(piece.end, others, tolerance):
        return [piece]
    halves = split_at(piece, [MIDPOINT_FRACTION])
    if len(halves) != 2:
        return [piece]
    return _homogeneous(halves[0], others, tolerance, depth - 1) + _homogeneous(halves[1], others, tolerance, depth - 1)


def _pieces(loops: Sequence[Loop], other: ChainIndex, tolerance: float) -> list[Segment]:
    found: list[Segment] = []
    reach = loops_box(other.loops) if other.items else None
    for loop in loops:
        for segment in loop:
            near = other.near(box_of(segment), tolerance) if reach is not None and boxes_meet(box_of(segment), reach, tolerance) else []
            if not near:  # nothing of the other chain is anywhere near: the piece stays whole
                if segment.start.distance_to(segment.end) > tolerance or isinstance(segment, ArcSegment):
                    found.append(segment)
                continue
            for piece in _cut(segment, near, tolerance):
                if piece.start.distance_to(piece.end) <= tolerance and not isinstance(piece, ArcSegment):
                    continue
                found += _homogeneous(piece, other.near(box_of(piece), tolerance), tolerance, CONTACT_SEARCH_STEPS)
    return found


def boolean(a: Sequence[Loop], b: Sequence[Loop], operation: str, tolerance: float = GEOMETRY_TOLERANCE_MM) -> list[Loop]:
    """INTERSECTION or DIFFERENCE (a minus b) of two regions, all loops oriented as described at the top.

    `tolerance`: pieces closer to each other than this lie on each other, and ends this close are one point. Exact chains need very
    little; a chain that came from polygons (arcs as chords) needs at least the chord deviation. Edges that nearly lie on each
    other (closer than a few tolerances, at a shallow angle) can make the pieces fail to close: the boolean is then tried again
    with a larger tolerance (`CHAIN_TOLERANCE_RETRIES`), and the error is raised only when that fails too."""
    try:
        return _boolean(a, b, operation, tolerance)
    except ChainError:
        for factor in CHAIN_TOLERANCE_RETRIES:
            try:
                return _boolean(a, b, operation, tolerance * factor)
            except ChainError:
                continue
        raise


def _classified(a: Sequence[Loop], b: Sequence[Loop], tolerance: float) -> tuple[list[Segment], list[Segment]]:
    """The pieces that make the intersection and the pieces that make the difference (a minus b), from one cutting and classifying."""
    inside_pieces: list[Segment] = []
    outside_pieces: list[Segment] = []
    index_a, index_b = ChainIndex(a), ChainIndex(b)
    reach = loops_box(b) if b else None
    for piece in _pieces(a, index_b, tolerance):
        if reach is None or not boxes_meet(box_of(piece), reach, tolerance):
            outside_pieces.append(piece)  # far from every piece of b: outside it (b lies within its box)
            continue
        middle = point_of(piece, MIDPOINT_FRACTION)
        where, other = index_b.locate(middle, tolerance)
        if where == ON:
            (inside_pieces if _same_way(piece, other, middle) else outside_pieces).append(piece)  # on a shared edge: the regions lie on the same side (intersection) or on opposite sides (difference)
        elif where == INSIDE:
            inside_pieces.append(piece)
        else:
            outside_pieces.append(piece)
    reach_a = loops_box(a) if a else None
    for piece in _pieces(b, index_a, tolerance):
        if reach_a is None or not boxes_meet(box_of(piece), reach_a, tolerance):
            continue  # far from every piece of a: outside it, part of neither result
        where, _other = index_a.locate(point_of(piece, MIDPOINT_FRACTION), tolerance)
        if where == INSIDE:
            inside_pieces.append(piece)
            outside_pieces.append(reversed_segment(piece))
    return inside_pieces, outside_pieces


def _boolean(a: Sequence[Loop], b: Sequence[Loop], operation: str, tolerance: float) -> list[Loop]:
    """One try of `boolean` with one tolerance."""
    inside_pieces, outside_pieces = _classified(a, b, tolerance)
    return _join(inside_pieces if operation == INTERSECTION else outside_pieces, 2 * tolerance)


def split_regions(a: Sequence[Loop], b: Sequence[Loop], tolerance: float = GEOMETRY_TOLERANCE_MM) -> tuple[list[Loop], list[Loop]]:
    """The intersection and the difference (a minus b) of two regions together: the cutting and classifying is done once.
    The tolerance is raised as in `boolean` when the pieces do not close."""
    for factor in (1, *CHAIN_TOLERANCE_RETRIES):
        try:
            inside_pieces, outside_pieces = _classified(a, b, tolerance * factor)
            return _join(inside_pieces, 2 * tolerance * factor), _join(outside_pieces, 2 * tolerance * factor)
        except ChainError:
            continue
    raise ChainError("the regions cannot be split")


def _union_pieces(a: Sequence[Loop], b: Sequence[Loop], tolerance: float) -> list[Segment]:
    """The pieces of the union: of each region the pieces outside the other one; a piece both borders share is kept once when the two
    regions lie on the same side of it, and dropped when they lie on opposite sides (the two regions join there)."""
    index_a, index_b = ChainIndex(a), ChainIndex(b)
    reach_a, reach_b = loops_box(a), loops_box(b)
    kept: list[Segment] = []
    for piece in _pieces(a, index_b, tolerance):
        if not boxes_meet(box_of(piece), reach_b, tolerance):
            kept.append(piece)  # far from every piece of b: outside it
            continue
        middle = point_of(piece, MIDPOINT_FRACTION)
        where, other = index_b.locate(middle, tolerance)
        if where == OUTSIDE or (where == ON and _same_way(piece, other, middle)):
            kept.append(piece)
    for piece in _pieces(b, index_a, tolerance):
        if not boxes_meet(box_of(piece), reach_a, tolerance) or index_a.locate(point_of(piece, MIDPOINT_FRACTION), tolerance)[0] == OUTSIDE:
            kept.append(piece)
    return kept


def union(a: Sequence[Loop], b: Sequence[Loop], tolerance: float = GEOMETRY_TOLERANCE_MM) -> list[Loop]:
    """The union of two regions (loops oriented as described at the top). The tolerance is raised as in `boolean` when the pieces do not
    close."""
    if not a or not b:
        return list(a or b)
    if not boxes_meet(loops_box(a), loops_box(b), tolerance):
        return [*a, *b]  # apart: both as they are
    for factor in (1, *CHAIN_TOLERANCE_RETRIES):
        try:
            return _join(_union_pieces(a, b, tolerance * factor), 2 * tolerance * factor)
        except ChainError:
            continue
    raise ChainError("the union cannot be worked out")


def union_all(regions: list[Sequence[Loop]], tolerance: float = GEOMETRY_TOLERANCE_MM) -> list[Loop]:
    """The union of many regions in one pass (faster than one `union` after the other): every piece of every region cut where it meets the
    others, kept when it lies outside all the others; a piece on the border of another region is kept by the first of the regions that
    lie on its same side, and dropped when one lies on its other side (they join there). Regions with no area are left out."""
    regions = [region for region in regions if region and abs(sum(loop_area(loop) for loop in region)) > tolerance * tolerance]
    if len(regions) <= 1:
        return list(regions[0]) if regions else []
    for factor in (1, *CHAIN_TOLERANCE_RETRIES):
        try:
            return _join(_union_all_pieces(regions, tolerance * factor), 2 * tolerance * factor)
        except ChainError:
            continue
    raise ChainError("the union cannot be worked out")


def _union_all_pieces(regions: list[Sequence[Loop]], tolerance: float) -> list[Segment]:
    indexes = [ChainIndex(region) for region in regions]
    boxes = [loops_box(region) for region in regions]
    every = ChainIndex([loop for region in regions for loop in region])
    kept: list[Segment] = []
    for number, region in enumerate(regions):
        for piece in _pieces(region, every, tolerance):
            middle = point_of(piece, MIDPOINT_FRACTION)
            keep = True
            for other, (index, box) in enumerate(zip(indexes, boxes)):
                if other == number or not boxes_meet((middle.x, middle.z, middle.x, middle.z), box, tolerance):
                    continue
                where, on = index.locate(middle, tolerance)
                if where == INSIDE:
                    keep = False
                elif where == ON:
                    keep = _same_way(piece, on, middle) and other > number  # kept once (by the first region), dropped where two regions join
                if not keep:
                    break
            if keep:
                kept.append(piece)
    return kept


def intersection(a: Sequence[Loop], b: Sequence[Loop], tolerance: float = GEOMETRY_TOLERANCE_MM) -> list[Loop]:
    return boolean(a, b, INTERSECTION, tolerance)


def difference(a: Sequence[Loop], b: Sequence[Loop], tolerance: float = GEOMETRY_TOLERANCE_MM) -> list[Loop]:
    return boolean(a, b, DIFFERENCE, tolerance)


class _Starts:
    """The start points of pieces in cells of the size of the tolerance: the piece that begins where another ends is found in the cells
    around that end (the first one of the list that is not used yet, as a search of the whole list would find it)."""

    def __init__(self, pieces: Sequence[Segment], tolerance: float) -> None:
        self.pieces, self.tolerance = pieces, tolerance
        self.size = max(tolerance, GEOMETRY_TOLERANCE_MM)
        self.used: set[int] = set()
        self.cells: dict[tuple[int, int], list[int]] = {}
        for number, piece in enumerate(pieces):
            self.cells.setdefault(self._cell(piece.start), []).append(number)

    def _cell(self, point: Point) -> tuple[int, int]:
        return math.floor(point.x / self.size), math.floor(point.z / self.size)

    def following(self, end: Point) -> int | None:
        i, j = self._cell(end)
        found = [
            number for di in (-1, 0, 1) for dj in (-1, 0, 1) for number in self.cells.get((i + di, j + dj), ())
            if number not in self.used and self.pieces[number].start.is_close(end, self.tolerance)
        ]
        if not found:
            return None
        self.used.add(min(found))
        return min(found)


def _join(pieces: Sequence[Segment], tolerance: float) -> list[Loop]:
    """The kept pieces joined end to end into closed loops (ends closer than `tolerance` are one point). Where the join accepted a gap, a short
    straight piece closes it, so every loop is closed exactly: a later operation then does not meet a gap it cannot bridge."""
    starts = _Starts(pieces, tolerance)
    loops: list[Loop] = []
    for first in range(len(pieces)):
        if first in starts.used:
            continue
        starts.used.add(first)
        chain = [pieces[first]]
        while not chain[-1].end.is_close(chain[0].start, tolerance):
            following = starts.following(chain[-1].end)
            if following is None:
                raise ChainError(f"the pieces do not close at ({chain[-1].end.x:.4f}, {chain[-1].end.z:.4f})")
            chain.append(pieces[following])
        ring: list[Segment] = []
        for index, piece in enumerate(chain):
            ring.append(piece)
            after = chain[(index + 1) % len(chain)]
            if not piece.end.is_close(after.start):
                ring.append(LineSegment(piece.end, after.start))
        loops.append(tuple(ring))
    return loops
