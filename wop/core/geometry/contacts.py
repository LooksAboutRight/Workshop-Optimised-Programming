"""Where a tool may stand along a straight move: the free stretches, found from the places where tool and part touch, not by a scan.

The tool moves by `s` times a unit vector. The set of positions where it penetrates the region changes only at an event: a corner of the
tool meets an edge of the region, a corner of the region meets an edge of the tool, or an arc and a line, or two arcs, are tangent. Each event
is a solution of a linear or quadratic equation. The events cut the move into pieces; inside a piece the tool is free or not at every place, so
a test at its middle and at its end says which (the end too: past a place where the tool only touches a piece it goes into it gradually, and
in the middle it may still be less deep than the tolerance). Free pieces that follow each other are one stretch, and its ends are events:
exact, with no step.

The events are collected from pairs of an edge of the tool and a piece of the region whose boxes meet when the tool is swept along the whole move.
"""

from __future__ import annotations

from collections.abc import Sequence

import math

from ..constants import CONTACT_POINT_SLACK_MM, GEOMETRY_TOLERANCE_MM
from .primitives import ArcSegment, LineSegment, Point, Segment
from .intersect import intersections
from .distance import distance_to_segment
from .chains import Box, box_of
from .penetration import RegionIndex, blocked_by_part
from .tool_edges import ToolLoop, placed, translated_segment

Vector = tuple[float, float]


def _dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _on(point: Point, segment: Segment) -> bool:
    return distance_to_segment(point, segment) <= CONTACT_POINT_SLACK_MM


def _ends(segment: Segment) -> list[Point]:
    return [segment.start, segment.end]


def _ray_events(point: Point, vector: Vector, length: float, piece: Segment, backwards: bool) -> list[float]:
    """The `s` at which `point + s v` (or `point - s v` when `backwards`) lies on the piece, for s from 0 to `length`."""
    sign = -1 if backwards else 1
    end = Point(point.x + sign * vector[0] * length, point.z + sign * vector[1] * length)
    return [point.distance_to(hit) for hit in intersections(LineSegment(point, end), piece)] if point.distance_to(end) > 0 else []


def _line_normal(line: LineSegment) -> Vector:
    dx, dz = line.end.x - line.start.x, line.end.z - line.start.z
    length = math.hypot(dx, dz)
    return -dz / length, dx / length


def _tangent_events(edge: Segment, other: Segment, vector: Vector, length: float) -> list[float]:
    """The `s` at which the edge of the tool (moved by s v) is tangent to the piece of the region, where the contact point lies on both."""
    found: list[float] = []
    if any(isinstance(piece, LineSegment) and piece.length <= GEOMETRY_TOLERANCE_MM for piece in (edge, other)):
        return found  # a line of no length is a point: its contacts are the corner events (`_ray_events`)

    def add(s: float, contact: Point) -> None:
        if -GEOMETRY_TOLERANCE_MM <= s <= length + GEOMETRY_TOLERANCE_MM and _on(contact, other) and _on(Point(contact.x - s * vector[0], contact.z - s * vector[1]), edge):
            found.append(min(max(s, 0), length))

    if isinstance(edge, ArcSegment) and isinstance(other, LineSegment):
        n = _line_normal(other)
        speed = _dot(n, vector)
        if abs(speed) > GEOMETRY_TOLERANCE_MM:
            for side in (1, -1):  # the centre of the arc at distance r from the line, on either side
                s = (side * edge.radius - _dot(n, (edge.center.x - other.start.x, edge.center.z - other.start.z))) / speed
                centre = Point(edge.center.x + s * vector[0], edge.center.z + s * vector[1])
                add(s, Point(centre.x - side * edge.radius * n[0], centre.z - side * edge.radius * n[1]))
    elif isinstance(edge, LineSegment) and isinstance(other, ArcSegment):
        n = _line_normal(edge)
        speed = _dot(n, vector)
        if abs(speed) > GEOMETRY_TOLERANCE_MM:
            for side in (1, -1):  # the centre of the region arc at distance R from the moved line
                s = (_dot(n, (other.center.x - edge.start.x, other.center.z - edge.start.z)) - side * other.radius) / speed
                add(s, Point(other.center.x - side * other.radius * n[0], other.center.z - side * other.radius * n[1]))
    elif isinstance(edge, ArcSegment) and isinstance(other, ArcSegment):
        w = (edge.center.x - other.center.x, edge.center.z - other.center.z)
        b = _dot(w, vector)
        for gap in (edge.radius + other.radius, abs(edge.radius - other.radius)):
            discriminant = b * b - (_dot(w, w) - gap * gap)
            if discriminant < 0:
                continue
            for s in (-b - math.sqrt(discriminant), -b + math.sqrt(discriminant)):
                centre = Point(edge.center.x + s * vector[0], edge.center.z + s * vector[1])
                span = centre.distance_to(other.center)
                if span > GEOMETRY_TOLERANCE_MM:
                    # outside each other, or the region circle inside the tool circle (the point is then on the far side)
                    side = -1 if gap < edge.radius + other.radius and edge.radius > other.radius else 1
                    ux, uz = side * (centre.x - other.center.x) / span, side * (centre.z - other.center.z) / span
                    add(s, Point(other.center.x + other.radius * ux, other.center.z + other.radius * uz))
    return found


def events(tool: Sequence[ToolLoop], keep: RegionIndex, vector: Vector, length: float) -> list[float]:
    """Every `s` in the move of the placed tool where a contact with the region begins or ends (with 0 and `length`), sorted."""
    found: list[float] = [0.0, length]
    for loop in tool:
        for edge in loop:
            x0, z0, x1, z1 = box_of(edge.segment)
            mx0, mz0, mx1, mz1 = box_of(translated_segment(edge.segment, vector[0] * length, vector[1] * length))
            reach: Box = (min(x0, mx0), min(z0, mz0), max(x1, mx1), max(z1, mz1))
            for other in keep.near(reach, GEOMETRY_TOLERANCE_MM):
                for corner in _ends(edge.segment):  # a corner of the tool runs into the piece
                    found += _ray_events(corner, vector, length, other, False)
                for corner in _ends(other):  # a corner of the region meets the moved tool edge
                    found += _ray_events(corner, vector, length, edge.segment, True)
                found += _tangent_events(edge.segment, other, vector, length)
    return sorted(s for s in found if -GEOMETRY_TOLERANCE_MM <= s <= length + GEOMETRY_TOLERANCE_MM)


def _parts(tool: Sequence[ToolLoop], keep: RegionIndex, start: Point, vector: Vector, length: float) -> list[tuple[float, float]]:
    """The move cut where a contact with the region begins or ends: inside one part the tool is everywhere free or everywhere blocked."""
    marks = [0.0]
    for s in events(placed(tool, start), keep, vector, length):
        if s - marks[-1] > GEOMETRY_TOLERANCE_MM:
            marks.append(min(s, length))
    if length - marks[-1] > GEOMETRY_TOLERANCE_MM:
        marks.append(length)
    return list(zip(marks, marks[1:]))


def _part_blocked(tool: Sequence[ToolLoop], keep: RegionIndex, start: Point, vector: Vector, part: tuple[float, float], tolerance: float) -> bool:
    s0, s1 = part
    return any(blocked_by_part(tool, keep, Point(start.x + vector[0] * s, start.z + vector[1] * s), tolerance) for s in ((s0 + s1) / 2, s1))


def first_free(tool: Sequence[ToolLoop], keep: RegionIndex, start: Point, vector: Vector, length: float, tolerance: float) -> tuple[float, float] | None:
    """The first part `(s0, s1)` of the move where the tool may stand (as `free_intervals`, but it stops there: a search for the first clear
    place need not test the rest of the move), None when there is none."""
    return next((part for part in _parts(tool, keep, start, vector, length) if not _part_blocked(tool, keep, start, vector, part, tolerance)), None)


def free_all_along(tool: Sequence[ToolLoop], keep: RegionIndex, start: Point, vector: Vector, length: float, tolerance: float) -> bool:
    """True when the tool may stand on every place of the move (it stops at the first part where it may not)."""
    return not any(_part_blocked(tool, keep, start, vector, part, tolerance) for part in _parts(tool, keep, start, vector, length))


def free_intervals(
    tool: Sequence[ToolLoop], keep: RegionIndex, start: Point, vector: Vector, length: float, tolerance: float, minimum: float,
) -> list[tuple[float, float]]:
    """The stretches `(s0, s1)` of the move from `start` along the unit vector `vector` where the tool (its tip at the start, a placed copy of the
    loops) may stand: it penetrates nothing deeper than `tolerance`. Stretches shorter than `minimum` are left out."""
    free: list[tuple[float, float]] = []
    for s0, s1 in _parts(tool, keep, start, vector, length):
        if _part_blocked(tool, keep, start, vector, (s0, s1), tolerance):
            continue
        if free and abs(free[-1][1] - s0) <= GEOMETRY_TOLERANCE_MM:
            free[-1] = (free[-1][0], s1)
        else:
            free.append((s0, s1))
    return [(a, b) for a, b in free if b - a >= minimum]
