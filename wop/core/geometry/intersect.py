"""Where two pieces of a sketch (lines, arcs, circles) cross, and how far along a piece a point is."""

from __future__ import annotations

import math

from ..constants import GEOMETRY_TOLERANCE_MM
from .primitives import ArcSegment, LineSegment, Point, Segment
from .distance import distance_to_segment


def fraction_along(segment: Segment, point: Point) -> float:
    """0 at the start and 1 at the end of the piece, for the point of the piece nearest to `point`.

    A point just before the start of an arc gives a small negative number. On a full circle the fraction is the
    angle from the start, 0 up to 1.
    """
    if isinstance(segment, LineSegment):
        dx, dz = segment.end.x - segment.start.x, segment.end.z - segment.start.z
        return ((point.x - segment.start.x) * dx + (point.z - segment.start.z) * dz) / (dx * dx + dz * dz)
    angle = math.atan2(point.z - segment.center.z, point.x - segment.center.x)
    along = ((angle - segment.start_angle) * segment.turn) % math.tau
    if segment.is_full_circle:
        return along / math.tau
    if along > (math.tau + segment.sweep) / 2:  # nearer the start from outside than the end: before the start
        along -= math.tau
    return along / segment.sweep


def _on_piece(segment: Segment, point: Point) -> bool:
    return distance_to_segment(point, segment) <= GEOMETRY_TOLERANCE_MM


def _line_line(a: LineSegment, b: LineSegment) -> list[Point]:
    d1 = (a.end.x - a.start.x, a.end.z - a.start.z)
    d2 = (b.end.x - b.start.x, b.end.z - b.start.z)
    denominator = d1[0] * d2[1] - d1[1] * d2[0]
    if denominator == 0:
        return []
    t = ((b.start.x - a.start.x) * d2[1] - (b.start.z - a.start.z) * d2[0]) / denominator
    u = ((b.start.x - a.start.x) * d1[1] - (b.start.z - a.start.z) * d1[0]) / denominator
    for along, (dx, dz) in ((t, d1), (u, d2)):  # the crossing lies on the line beyond an end of the piece: off it (as `_on_piece` says, without the distance)
        if max(-along, along - 1) * math.hypot(dx, dz) > GEOMETRY_TOLERANCE_MM:
            return []
    x, z = a.start.x + d1[0] * t, a.start.z + d1[1] * t
    for line, (dx, dz) in ((a, d1), (b, d2)):  # a line along an axis keeps its coordinate exactly (no 39.99999 for 40)
        if dx == 0:
            x = line.start.x
        if dz == 0:
            z = line.start.z
    return [Point(x, z)]


def _line_circle(line: LineSegment, centre: Point, radius: float) -> list[Point]:
    dx, dz = line.end.x - line.start.x, line.end.z - line.start.z
    fx, fz = line.start.x - centre.x, line.start.z - centre.z
    a = dx * dx + dz * dz
    half_b = fx * dx + fz * dz
    c = fx * fx + fz * fz - radius * radius
    discriminant = half_b * half_b - a * c
    if discriminant < 0:
        return []
    root = math.sqrt(discriminant)
    ts = sorted({(-half_b - root) / a, (-half_b + root) / a})
    return [Point(line.start.x + dx * t, line.start.z + dz * t) for t in ts]


def _circle_circle(c1: Point, r1: float, c2: Point, r2: float) -> list[Point]:
    distance = c1.distance_to(c2)
    if distance == 0 or distance > r1 + r2 or distance < abs(r1 - r2):
        return []
    along = (r1 * r1 - r2 * r2 + distance * distance) / (2 * distance)
    height = math.sqrt(max(0, r1 * r1 - along * along))
    ux, uz = (c2.x - c1.x) / distance, (c2.z - c1.z) / distance
    base = Point(c1.x + ux * along, c1.z + uz * along)
    if height == 0:
        return [base]
    return [Point(base.x - uz * height, base.z + ux * height), Point(base.x + uz * height, base.z - ux * height)]


def intersections(a: Segment, b: Segment) -> list[Point]:
    """The points where the two pieces cross or touch (only points that lie on both pieces)."""
    if isinstance(a, LineSegment):
        candidates = _line_line(a, b) if isinstance(b, LineSegment) else _line_circle(a, b.center, b.radius)
    elif isinstance(b, LineSegment):
        candidates = _line_circle(b, a.center, a.radius)
    else:
        candidates = _circle_circle(a.center, a.radius, b.center, b.radius)
    return [p for p in candidates if _on_piece(a, p) and _on_piece(b, p)]


def point_of(segment: Segment, fraction: float) -> Point:
    """The point at a fraction along the piece (also for a full circle, where it runs from the start all round)."""
    if isinstance(segment, ArcSegment) and segment.is_full_circle:
        angle = segment.start_angle + segment.turn * math.tau * fraction
        return Point(segment.center.x + segment.radius * math.cos(angle), segment.center.z + segment.radius * math.sin(angle))
    return segment.point_at(fraction)
