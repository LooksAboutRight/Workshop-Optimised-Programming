"""Pieces moved sideways by the same distance: lines along their normal, arcs keep their centre and change their radius. Where two moved
pieces do not meet: on the outer side of a turn a round join (an arc around the old corner) closes the gap; on the inner side both pieces
are cut back to where their curves cross; where no crossing exists a straight line joins the two ends."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..constants import GEOMETRY_TOLERANCE_MM
from .primitives import ArcDirection, ArcSegment, LineSegment, Point, Segment


@dataclass
class _Piece:
    segment: Segment
    original: Segment
    step_index: int


def _unit(dx: float, dz: float) -> tuple[float, float]:
    length = math.hypot(dx, dz)
    return dx / length, dz / length


def tangent_at_start(segment: Segment) -> tuple[float, float]:
    if isinstance(segment, LineSegment):
        return _unit(segment.end.x - segment.start.x, segment.end.z - segment.start.z)
    return _arc_tangent(segment, segment.start)


def tangent_at_end(segment: Segment) -> tuple[float, float]:
    if isinstance(segment, LineSegment):
        return tangent_at_start(segment)
    return _arc_tangent(segment, segment.end)


def _arc_tangent(arc: ArcSegment, at: Point) -> tuple[float, float]:
    rx, rz = at.x - arc.center.x, at.z - arc.center.z
    turn = arc.turn  # counter-clockwise in (x, z): the tangent is the radius turned a quarter turn
    return _unit(-rz * turn, rx * turn)


def _moved(segment: Segment, distance: float) -> Segment | None:
    """The segment moved to its left by `distance` (None: an arc whose radius shrinks to nothing)."""
    if isinstance(segment, LineSegment):
        tx, tz = tangent_at_start(segment)
        nx, nz = tz, -tx  # to the left in the picture
        return LineSegment(Point(segment.start.x + nx * distance, segment.start.z + nz * distance),
                           Point(segment.end.x + nx * distance, segment.end.z + nz * distance))
    radius = segment.radius + distance * segment.turn  # clockwise in (x, z): left is towards the centre
    if radius <= GEOMETRY_TOLERANCE_MM:
        return None
    scale = radius / segment.radius

    def onto(point: Point) -> Point:
        return Point(segment.center.x + (point.x - segment.center.x) * scale,
                     segment.center.z + (point.z - segment.center.z) * scale)

    return ArcSegment(onto(segment.start), onto(segment.end), segment.center, segment.direction)


def _circle_of(segment: Segment) -> tuple[Point, float] | None:
    return (segment.center, segment.radius) if isinstance(segment, ArcSegment) else None


def _crossings(a: Segment, b: Segment) -> list[Point]:
    """Where the full lines / circles of two segments cross."""
    circle_a, circle_b = _circle_of(a), _circle_of(b)
    if circle_a is None and circle_b is None:
        ax, az = a.start.x, a.start.z
        dax, daz = a.end.x - ax, a.end.z - az
        dbx, dbz = b.end.x - b.start.x, b.end.z - b.start.z
        denominator = dax * dbz - daz * dbx
        if abs(denominator) <= GEOMETRY_TOLERANCE_MM:
            return []
        t = ((b.start.x - ax) * dbz - (b.start.z - az) * dbx) / denominator
        return [Point(ax + dax * t, az + daz * t)]
    if circle_a is None or circle_b is None:
        line, (centre, radius) = (a, circle_b) if circle_a is None else (b, circle_a)
        dx, dz = line.end.x - line.start.x, line.end.z - line.start.z
        fx, fz = line.start.x - centre.x, line.start.z - centre.z
        quad_a, half_b, quad_c = dx * dx + dz * dz, fx * dx + fz * dz, fx * fx + fz * fz - radius * radius
        discriminant = half_b * half_b - quad_a * quad_c
        if discriminant < 0:
            return []
        root = math.sqrt(discriminant)
        return [Point(line.start.x + dx * t, line.start.z + dz * t)
                for t in ((-half_b - root) / quad_a, (-half_b + root) / quad_a)]
    (c1, r1), (c2, r2) = circle_a, circle_b
    distance = c1.distance_to(c2)
    if distance <= GEOMETRY_TOLERANCE_MM or distance > r1 + r2 or distance < abs(r1 - r2):
        return []
    along = (r1 * r1 - r2 * r2 + distance * distance) / (2 * distance)
    height = math.sqrt(max(0.0, r1 * r1 - along * along))
    ux, uz = (c2.x - c1.x) / distance, (c2.z - c1.z) / distance
    mx, mz = c1.x + ux * along, c1.z + uz * along
    return [Point(mx - uz * height, mz + ux * height), Point(mx + uz * height, mz - ux * height)]


def _with_end(segment: Segment, end: Point) -> Segment:
    if isinstance(segment, LineSegment):
        return LineSegment(segment.start, end)
    return ArcSegment(segment.start, end, segment.center, segment.direction)


def _with_start(segment: Segment, start: Point) -> Segment:
    if isinstance(segment, LineSegment):
        return LineSegment(start, segment.end)
    return ArcSegment(start, segment.end, segment.center, segment.direction)


def _join(first: _Piece, second: _Piece) -> list[Segment]:
    """Make the end of `first` meet the start of `second` (may cut both back); returns what must be put between them."""
    end, start = first.segment.end, second.segment.start
    if end.is_close(start):
        return []
    corner = first.original.end
    gap_x, gap_z = start.x - end.x, start.z - end.z
    tx, tz = tangent_at_end(first.original)  # the moved piece runs the same way; it may be cut back to nothing by the corner before
    if gap_x * tx + gap_z * tz > 0:  # the outer side of a turn: a round join around the old corner
        bx, bz = tangent_at_start(second.original)
        ax, az = tangent_at_end(first.original)
        direction = ArcDirection.CCW if ax * bz - az * bx > 0 else ArcDirection.CW
        return [ArcSegment(end, start, corner, direction)]
    crossings = _crossings(first.segment, second.segment)
    if crossings:
        cross = min(crossings, key=lambda point: point.distance_to(corner))
        first.segment = _with_end(first.segment, cross)
        second.segment = _with_start(second.segment, cross)
        return []
    return [LineSegment(end, start)]


def offset_segments(
    tagged: list[tuple[int, Segment]], distance_mm: float, closed: bool
) -> list[tuple[int, Segment]]:
    """The segments moved to their left by `distance_mm`, joined; the step index of every piece is kept."""
    pieces: list[_Piece] = []
    for index, segment in tagged:
        moved = _moved(segment, distance_mm)
        if moved is not None:
            pieces.append(_Piece(moved, segment, index))
    if not pieces:
        return []
    result: list[tuple[int, Segment]] = []
    between: dict[int, list[Segment]] = {}
    pairs = len(pieces) if closed else len(pieces) - 1
    for number in range(pairs):
        first, second = pieces[number], pieces[(number + 1) % len(pieces)]
        if first is second:
            continue
        between[number] = _join(first, second)
    for number, piece in enumerate(pieces):
        result.append((piece.step_index, piece.segment))
        result.extend((piece.step_index, extra) for extra in between.get(number, []))
    return result
