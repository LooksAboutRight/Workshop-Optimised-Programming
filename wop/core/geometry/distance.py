"""How far a point is from a line or an arc."""

from __future__ import annotations

import math

from .primitives import ArcSegment, Point, Segment


def distance_to_segment(position: Point, segment: Segment) -> float:
    if isinstance(segment, ArcSegment):
        return _distance_to_arc(position, segment)
    dx, dz = segment.end.x - segment.start.x, segment.end.z - segment.start.z
    length_squared = dx * dx + dz * dz
    if length_squared == 0:
        return position.distance_to(segment.start)
    t = max(0.0, min(1.0, ((position.x - segment.start.x) * dx + (position.z - segment.start.z) * dz) / length_squared))
    return math.hypot(position.x - segment.start.x - dx * t, position.z - segment.start.z - dz * t)


def _distance_to_arc(position: Point, arc: ArcSegment) -> float:
    if position.is_close(arc.center, 0):
        return arc.radius
    angle = math.atan2(position.z - arc.center.z, position.x - arc.center.x)
    along = ((angle - arc.start_angle) * arc.turn) % math.tau
    if arc.is_full_circle or along <= arc.sweep:
        return abs(position.distance_to(arc.center) - arc.radius)
    return min(position.distance_to(arc.start), position.distance_to(arc.end))
