"""Where a point lies on a curve made of lines and arcs (`locate`): the piece, how far along it, and how far the point is from it."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import FOLLOW_SNAP_MM
from .geometry import LineSegment, Point, Segment


@dataclass(frozen=True)
class Location:
    """A point on the curve: the piece it lies on, how far along that piece (0 to 1), the point and its distance from where
    it was asked for."""

    index: int
    fraction: float
    point: Point
    distance: float


def _nearest(piece: Segment, point: Point) -> tuple[float, Point, float]:
    """(fraction, nearest point, distance) of the piece for `point`."""
    if isinstance(piece, LineSegment):
        dx, dz = piece.end.x - piece.start.x, piece.end.z - piece.start.z
        square = dx * dx + dz * dz
        t = 0.0 if square <= 0 else max(0.0, min(1.0, ((point.x - piece.start.x) * dx + (point.z - piece.start.z) * dz) / square))
    else:
        angle = math.atan2(point.z - piece.center.z, point.x - piece.center.x)
        travelled = ((angle - piece.start_angle) * piece.turn) % math.tau
        sweep = piece.sweep
        if travelled <= sweep:
            t = travelled / sweep
        else:  # beyond the ends: the nearer end
            t = 0.0 if (math.tau - travelled) < (travelled - sweep) else 1.0
    nearest = piece.point_at(t)
    return t, nearest, nearest.distance_to(point)


def locate(pieces: list[Segment], point: Point, snap_mm: float = FOLLOW_SNAP_MM) -> Location | None:
    """The place on the curve nearest to `point`, or None when the curve is further away than `snap_mm`."""
    best: Location | None = None
    for index, piece in enumerate(pieces):
        fraction, nearest, distance = _nearest(piece, point)
        if best is None or distance < best.distance:
            best = Location(index, fraction, nearest, distance)
    return best if best is not None and best.distance <= snap_mm else None
