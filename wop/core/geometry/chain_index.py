"""Where things lie on chains of lines and arcs (`chains.py`): a piece cut at fractions of its length, where a line at a level crosses the
loops, the exact box of a piece, and `ChainIndex`, the pieces of some loops with their boxes, made once, so that the question "which pieces
are near this?" skips the many that are far. The boolean of `chains.py` and the tests of the planner (`penetration.py`) are built on it."""

from __future__ import annotations

from collections.abc import Sequence

import math
from bisect import bisect_right

from ..constants import GEOMETRY_TOLERANCE_MM, MIDPOINT_FRACTION
from .primitives import ArcDirection, ArcSegment, LineSegment, Point, Segment
from .intersect import fraction_along, point_of
from .distance import distance_to_segment

Loop = Sequence[Segment]  # a closed loop: a tuple (as the booleans make it) or a list
INSIDE, OUTSIDE, ON = "inside", "outside", "on"


# --- cutting a piece --------------------------------------------------------------------------------

def split_at(segment: Segment, marks: list[float]) -> list[Segment]:
    """The piece cut at the given fractions (the ones at the ends or doubled are ignored). Arcs stay arcs."""
    cuts: list[Point] = [segment.start]
    for mark in sorted(m for m in marks if 0 < m < 1):
        point = point_of(segment, mark)
        if not point.is_close(cuts[-1]) and not point.is_close(segment.end):
            cuts.append(point)
    cuts.append(segment.end)
    if len(cuts) == 2 and isinstance(segment, ArcSegment) and segment.is_full_circle:
        return [segment]
    return [
        LineSegment(a, b) if isinstance(segment, LineSegment) else ArcSegment(a, b, segment.center, segment.direction)
        for a, b in zip(cuts, cuts[1:])
    ]


# --- where a line crosses the loops ---------------------------------------------------------------

def coordinates(point: Point, axis: int) -> tuple[float, float]:
    """(along the level axis, along the line): axis 0 = lines at constant radius, axis 1 = lines at constant Z."""
    return (point.x, point.z) if axis == 0 else (point.z, point.x)


def monotone(segment: Segment, axis: int) -> list[Segment]:
    """A line is monotone; an arc is cut at the places where its coordinate along `axis` is largest or smallest."""
    if isinstance(segment, LineSegment):
        return [segment]
    reach = [
        Point(segment.center.x + sign * segment.radius, segment.center.z) if axis == 0
        else Point(segment.center.x, segment.center.z + sign * segment.radius)
        for sign in (1, -1)
    ]
    marks = [fraction_along(segment, p) for p in reach if distance_to_segment(p, segment) <= GEOMETRY_TOLERANCE_MM]
    return split_at(segment, marks)


def crossing_value(piece: Segment, level: float, axis: int) -> float:
    a0, b0 = coordinates(piece.start, axis)
    a1, b1 = coordinates(piece.end, axis)
    if isinstance(piece, LineSegment):
        return b0 + (level - a0) / (a1 - a0) * (b1 - b0)
    centre_a, centre_b = coordinates(piece.center, axis)
    ratio = max(-1, min(1, (level - centre_a) / piece.radius))
    offset = piece.radius * math.sqrt(1 - ratio * ratio)
    _middle_a, middle_b = coordinates(point_of(piece, MIDPOINT_FRACTION), axis)
    return centre_b + (offset if middle_b >= centre_b else -offset)


def crossings(loops: Sequence[Loop], level: float, axis: int) -> list[float]:
    """Where a line at `level` crosses the loops, sorted along the line. A piece that only ends on the line counts on one
    side only, so a corner on the line is counted once and a touch from outside not at all."""
    found: list[float] = []
    for loop in loops:
        for segment in loop:
            for piece in monotone(segment, axis):
                a0, _b0 = coordinates(piece.start, axis)
                a1, _b1 = coordinates(piece.end, axis)
                if (a0 > level + GEOMETRY_TOLERANCE_MM) != (a1 > level + GEOMETRY_TOLERANCE_MM):  # a value within the tolerance of the level is on it: an edge along the level is no crossing
                    found.append(crossing_value(piece, level, axis))
    return sorted(found)


# --- boxes: most pieces of two chains are far from each other ----------------------------------------

Box = tuple[float, float, float, float]  # smallest x, smallest z, largest x, largest z


def box_of(segment: Segment) -> Box:
    """The exact box of a line or an arc (an arc includes the extreme points of its circle that lie on it). Segments never change, so
    the box is worked out once and kept on the segment (its field `box`, not compared: equality and hashing do not see it)."""
    box = segment.box
    if box is None:
        box = _box_of(segment)
        object.__setattr__(segment, "box", box)
    return box


def _box_of(segment: Segment) -> Box:
    points = [segment.start, segment.end]
    if isinstance(segment, ArcSegment):
        radius = segment.radius
        first = segment.start_angle if segment.direction is ArcDirection.CCW else segment.end_angle
        sweep = segment.sweep
        for angle in (0, math.pi / 2, math.pi, -math.pi / 2):
            if (angle - first) % math.tau <= sweep + GEOMETRY_TOLERANCE_MM:
                points.append(Point(segment.center.x + radius * math.cos(angle), segment.center.z + radius * math.sin(angle)))
    return min(p.x for p in points), min(p.z for p in points), max(p.x for p in points), max(p.z for p in points)


def boxes_meet(a: Box, b: Box, margin: float) -> bool:
    ax0, az0, ax1, az1 = a
    bx0, bz0, bx1, bz1 = b
    return ax0 <= bx1 + margin and bx0 <= ax1 + margin and az0 <= bz1 + margin and bz0 <= az1 + margin


def loops_box(loops: Sequence[Loop]) -> Box:
    """The exact box of loops (or of any chains): arcs count with the extreme points of their circles."""
    x_low, z_low, x_high, z_high = zip(*[box_of(segment) for loop in loops for segment in loop])
    return min(x_low), min(z_low), max(x_high), max(z_high)


class _Grid:
    """The boxes of the pieces sorted into the cells of a grid over their common box (about as many cells as pieces): a question about a
    box looks only at the pieces listed in the cells it covers."""

    def __init__(self, boxes: list[Box]) -> None:
        x_low, z_low, x_high, z_high = zip(*boxes)
        self.x0, self.z0, self.x1, self.z1 = min(x_low), min(z_low), max(x_high), max(z_high)
        self.side = max(1, math.isqrt(len(boxes)))
        self.width = max(self.x1 - self.x0, GEOMETRY_TOLERANCE_MM) / self.side
        self.height = max(self.z1 - self.z0, GEOMETRY_TOLERANCE_MM) / self.side
        self.cells: dict[tuple[int, int], list[int]] = {}
        for number, box in enumerate(boxes):
            for cell in self._cells(box, 0.0):
                self.cells.setdefault(cell, []).append(number)

    def _cells(self, box: Box, margin: float) -> list[tuple[int, int]]:
        last = self.side - 1
        x0, z0, x1, z1 = box
        i0 = min(last, max(0, int((x0 - margin - self.x0) / self.width)))
        i1 = min(last, max(0, int((x1 + margin - self.x0) / self.width)))
        j0 = min(last, max(0, int((z0 - margin - self.z0) / self.height)))
        j1 = min(last, max(0, int((z1 + margin - self.z0) / self.height)))
        return [(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]

    def candidates(self, box: Box, margin: float) -> list[int]:
        """The numbers of the pieces that may meet the box (in their order), a few more than do."""
        if not boxes_meet(box, (self.x0, self.z0, self.x1, self.z1), margin):
            return []
        found: set[int] = set()
        for cell in self._cells(box, margin):
            found.update(self.cells.get(cell, ()))
        return sorted(found)


class _Slabs:
    """The pieces whose range along one axis contains a value: the axis cut at every end of a range into slabs, each slab with the pieces
    that cover it, so the question is one search in a sorted list."""

    def __init__(self, ranges: list[tuple[float, float]]) -> None:
        self.ranges = ranges
        self.bounds = sorted({value for pair in ranges for value in pair})
        self.slabs: list[list[int]] = [[] for _ in self.bounds]
        for number, (low, high) in enumerate(ranges):
            first, last = bisect_right(self.bounds, low) - 1, bisect_right(self.bounds, high) - 1
            for slab in range(first, last + 1):
                self.slabs[slab].append(number)

    def covering(self, level: float) -> list[int]:
        slab = bisect_right(self.bounds, level) - 1
        if slab < 0 or level > self.bounds[-1]:
            return []
        return [number for number in self.slabs[slab] if self.ranges[number][0] <= level <= self.ranges[number][1]]


class ChainIndex:
    """The pieces of some loops with their boxes, made once: asking which pieces are near something skips the many that are far (a grid
    of the boxes and, for the rays of the inside test, slabs along each axis; both made when first needed)."""

    def __init__(self, loops: Sequence[Loop]) -> None:
        self.loops = list(loops)
        self.items = [(box_of(segment), segment) for loop in loops for segment in loop]
        self._grid: _Grid | None = None
        self._slabs: dict[int, _Slabs] = {}

    def near(self, box: Box, margin: float) -> list[Segment]:
        if not self.items:
            return []
        if self._grid is None:
            self._grid = _Grid([item_box for item_box, _segment in self.items])
        items = self.items
        return [items[n][1] for n in self._grid.candidates(box, margin) if boxes_meet(box, items[n][0], margin)]

    def crossings(self, level: float, axis: int) -> list[float]:
        """Where a line at `level` crosses the loops (see `crossings`), looking only at the pieces whose box the line meets."""
        index = 0 if axis == 0 else 1
        if not self.items:
            return []
        if index not in self._slabs:
            self._slabs[index] = _Slabs([(box[index], box[index + 2]) for box, _segment in self.items])
        pieces = [self.items[n][1] for n in self._slabs[index].covering(level)]
        return crossings([tuple(pieces)], level, axis)

    def inside(self, point: Point) -> bool:
        """Even-odd test with a ray towards larger Z. A ray that runs within a hair of a corner of the border (an end of a piece, an extreme of
        an arc) can count that corner wrongly; it is moved off it by a few millionths of a millimetre first (the callers ask about points much
        further than that from the border, so the answer is the same)."""
        level = point.x
        margin = 2 * GEOMETRY_TOLERANCE_MM
        for shift in (0.0, 2 * margin, -2 * margin):
            if not self._near_a_corner(level + shift, margin):
                level += shift
                break
        return sum(1 for z in self.crossings(level, 0) if z > point.z) % 2 == 1

    def _near_a_corner(self, level: float, margin: float) -> bool:
        if not self.items:
            return False
        if 0 not in self._slabs:
            self._slabs[0] = _Slabs([(box[0], box[2]) for box, _segment in self.items])
        for number in self._slabs[0].covering(level):
            for piece in monotone(self.items[number][1], 0):
                if abs(piece.start.x - level) <= margin or abs(piece.end.x - level) <= margin:
                    return True
        return False

    def locate(self, point: Point, tolerance: float) -> tuple[str, Segment | None]:
        for segment in self.near((point.x, point.z, point.x, point.z), tolerance):
            if distance_to_segment(point, segment) <= tolerance:
                return ON, segment
        return (INSIDE if self.inside(point) else OUTSIDE), None
