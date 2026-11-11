"""Check a contour before use (requirement C8): crossing segments (`find_crossings`). A sketch has no gaps: its pieces share their points."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    ANGLE_TOLERANCE_RAD,
    CROSSING_CHECK_ARC_DEVIATION_MM,
    GEOMETRY_TOLERANCE_MM,
    MIN_SEGMENTS_FOR_CROSSING_CHECK,
)
from .geometry import (
    ArcSegment,
    Point,
    Segment,
    segments_intersect,
)


@dataclass(frozen=True)
class Crossing:
    """Two segments (by index) that cross or touch where they should not."""

    first: int
    second: int


def _polyline(segment: Segment) -> list[Point]:
    if isinstance(segment, ArcSegment):
        return segment.to_polyline(CROSSING_CHECK_ARC_DEVIATION_MM)
    return [segment.start, segment.end]


@dataclass(frozen=True)
class _Box:
    """Bounding box of a polyline, used to skip pairs that cannot touch."""

    min_x: float
    min_z: float
    max_x: float
    max_z: float


def _box(points: list[Point]) -> _Box:
    return _Box(
        min(p.x for p in points),
        min(p.z for p in points),
        max(p.x for p in points),
        max(p.z for p in points),
    )


def _boxes_overlap(a: _Box, b: _Box) -> bool:
    tolerance = GEOMETRY_TOLERANCE_MM
    return (
        a.min_x <= b.max_x + tolerance
        and b.min_x <= a.max_x + tolerance
        and a.min_z <= b.max_z + tolerance
        and b.min_z <= a.max_z + tolerance
    )


def _folds_back(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """True if two chords that meet at a joint run back over each other."""
    length_p = p1.distance_to(p2)
    length_q = q1.distance_to(q2)
    if length_p <= GEOMETRY_TOLERANCE_MM or length_q <= GEOMETRY_TOLERANCE_MM:
        return False
    ux, uz = (p2.x - p1.x) / length_p, (p2.z - p1.z) / length_p
    wx, wz = (q2.x - q1.x) / length_q, (q2.z - q1.z) / length_q
    return abs(ux * wz - uz * wx) <= ANGLE_TOLERANCE_RAD and ux * wx + uz * wz < 0


def _polylines_cross(first: list[Point], second: list[Point], adjacent: bool) -> bool:
    """Do the two polylines cross or touch? Adjacent ones may meet at their joint."""
    for i in range(len(first) - 1):
        for j in range(len(second) - 1):
            at_joint = adjacent and i == len(first) - 2 and j == 0
            if at_joint:
                if _folds_back(first[i], first[i + 1], second[j], second[j + 1]):
                    return True
                continue
            if segments_intersect(first[i], first[i + 1], second[j], second[j + 1]):
                return True
    return False


def find_crossings(segments: list[Segment], closed: bool) -> list[Crossing]:
    """Segments that cross or touch each other other than at the joints of the chain."""
    count = len(segments)
    if count < MIN_SEGMENTS_FOR_CROSSING_CHECK:
        return []
    polylines = [_polyline(segment) for segment in segments]
    boxes = [_box(points) for points in polylines]
    crossings: list[Crossing] = []
    for i in range(count):
        for j in range(i + 1, count):
            if not _boxes_overlap(boxes[i], boxes[j]):
                continue
            follows = j == i + 1
            wraps = closed and i == 0 and j == count - 1
            if wraps:
                crossing = _polylines_cross(polylines[j], polylines[i], adjacent=True)
            else:
                crossing = _polylines_cross(polylines[i], polylines[j], adjacent=follows)
            if crossing:
                crossings.append(Crossing(i, j))
    return crossings


