"""Whether the nose of a tool can follow a contour: the test behind the note of the finishing pass ("needs a nose radius of N mm or smaller").

The finishing pass follows the contour whatever the tool can do (the user's rule, 2026-10-23): it never leaves a piece out and never moves off
the contour on its own. Where the nose cannot follow (a concave arc smaller than the nose, a groove narrower than the nose), the block says so
and names the largest nose radius that would; the user changes the tool and everything is planned again.

The nose follows the contour when its circle, moved along the path of its centre (the contour moved to its free side by the radius,
`geometry/offset.py`), touches every point of the contour and cuts into the part nowhere. A sharp inner corner is the one
place it cannot touch, whatever its size: the nose leaves its own radius there, which is what a drawn sharp inner corner means.
"""

from __future__ import annotations

import math

from ..constants import NOSE_FOLLOW_SAMPLE_MM, NOSE_FOLLOW_TOLERANCE_MM, NOSE_RADIUS_SEARCH_STEPS
from ..geometry.offset import offset_segments, tangent_at_end, tangent_at_start
from ..geometry import Point, Segment
from ..geometry.intersect import fraction_along, point_of
from ..geometry.distance import distance_to_segment

STRAIGHT_ON = 1 - 1e-9  # two pieces whose tangents agree this well meet without a corner


def _samples(segment: Segment) -> list[Point]:
    count = max(2, math.ceil(segment.length / NOSE_FOLLOW_SAMPLE_MM))
    return [point_of(segment, i / count) for i in range(count + 1)]


def _distance(point: Point, pieces: list[Segment]) -> float:
    return min(distance_to_segment(point, piece) for piece in pieces)


def misses(path: list[Segment], outside: bool, radius: float) -> list[Point]:
    """The points of the contour the nose of this radius does not follow: points it cannot touch and points where it cuts into the part
    (given as the point of the contour nearest to it). Empty when it follows the whole contour."""
    if radius <= NOSE_FOLLOW_TOLERANCE_MM or not path:
        return []
    centre = [segment for _index, segment in offset_segments(list(enumerate(path)), -radius if outside else radius, closed=False)]
    if not centre:
        return [path[0].start]
    found: list[Point] = []
    for segment in centre:  # the nose cuts into the part where its centre comes nearer to the contour than its radius
        for point in _samples(segment):
            if _distance(point, path) < radius - NOSE_FOLLOW_TOLERANCE_MM:
                found.append(_nearest(point, path))
    corners = []  # sharp inner corners: (corner, how far from it the nose cannot touch the pieces either side)
    for before, after in zip(path, path[1:]):
        a, b = tangent_at_end(before), tangent_at_start(after)
        if a[0] * b[0] + a[1] * b[1] < STRAIGHT_ON:
            far = _distance(before.end, centre)
            if far > radius + NOSE_FOLLOW_TOLERANCE_MM:
                corners.append((before.end, math.sqrt(far * far - radius * radius) + NOSE_FOLLOW_TOLERANCE_MM))
    for segment in path:  # every other point of the contour the nose touches: its centre is the radius away
        for point in _samples(segment):
            if any(point.distance_to(corner) <= reach for corner, reach in corners):
                continue
            if _distance(point, centre) > radius + NOSE_FOLLOW_TOLERANCE_MM:
                found.append(point)
    return found


def _nearest(point: Point, path: list[Segment]) -> Point:
    """The point of the contour nearest to `point`."""
    piece = min(path, key=lambda segment: distance_to_segment(point, segment))
    return point_of(piece, min(max(fraction_along(piece, point), 0.0), 1.0))


def largest_following_radius(path: list[Segment], outside: bool, radius: float) -> float:
    """The largest nose radius up to `radius` that follows the whole contour (0 when only a sharp tool would)."""
    low, high = 0.0, radius
    for _ in range(NOSE_RADIUS_SEARCH_STEPS):
        middle = (low + high) / 2
        if misses(path, outside, middle):
            high = middle
        else:
            low = middle
    return low
