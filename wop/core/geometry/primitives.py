"""2D geometry primitives for the X/Z plane.

Coordinates: x is the RADIUS (distance from the spindle axis), z is the
position along the axis. All lengths are millimetres.

Angles are measured in the (x, z) plane, counter-clockwise from the +x axis
towards the +z axis. Mapping arc directions to G2/G3 is the job of the
postprocessor, not of this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from ..constants import (
    ARC_MAX_DEVIATION_MM,
    GEOMETRY_TOLERANCE_MM,
    MAX_ARC_SEGMENT_ANGLE_RAD,
)


Box = tuple[float, float, float, float]  # smallest x, smallest z, largest x, largest z


# The classes below may be compiled (tools/build_compiled.py, mypyc): then they have no free attributes, so what is kept on a piece is a
# field that is not given when the piece is made (`init=False`) and not compared; `__reduce__` and `__deepcopy__` keep pickling and
# copying working (a value that never changes is its own copy).

@dataclass(frozen=True)
class Point:
    x: float  # radius, mm
    z: float  # axial position, mm

    def distance_to(self, other: Point) -> float:
        return math.hypot(self.x - other.x, self.z - other.z)

    def is_close(self, other: Point, tolerance: float = GEOMETRY_TOLERANCE_MM) -> bool:
        return math.hypot(self.x - other.x, self.z - other.z) <= tolerance

    def __reduce__(self) -> tuple[object, tuple[float, float]]:
        return (Point, (self.x, self.z))

    def __deepcopy__(self, memo: dict[int, object]) -> Point:
        return self


class ArcDirection(Enum):
    """Direction of travel along an arc in the (x, z) plane."""

    CCW = 1
    CW = -1


@dataclass(frozen=True)
class LineSegment:
    start: Point
    end: Point
    box: Box | None = field(default=None, init=False, repr=False, compare=False)  # kept by `chain_index.box_of`

    def __post_init__(self) -> None:
        object.__setattr__(self, "box", None)  # a compiled class does not fill a field that is not given

    @property
    def length(self) -> float:
        return self.start.distance_to(self.end)

    def point_at(self, t: float) -> Point:
        """Point at parameter t (0 = start, 1 = end)."""
        return Point(
            self.start.x * (1 - t) + self.end.x * t,
            self.start.z * (1 - t) + self.end.z * t,
        )

    def __reduce__(self) -> tuple[object, tuple[Point, Point]]:
        return (LineSegment, (self.start, self.end))

    def __deepcopy__(self, memo: dict[int, object]) -> LineSegment:
        return self


@dataclass(frozen=True)
class ArcSegment:
    """Circular arc from start to end around center.

    If start and end are the same point, the arc is a full circle. An arc never changes: its radius, angles, sweep and
    length are worked out when it is made (fields that are not given and not compared).
    """

    start: Point
    end: Point
    center: Point
    direction: ArcDirection
    radius: float = field(default=0.0, init=False, repr=False, compare=False)
    is_full_circle: bool = field(default=False, init=False, repr=False, compare=False)
    start_angle: float = field(default=0.0, init=False, repr=False, compare=False)
    end_angle: float = field(default=0.0, init=False, repr=False, compare=False)
    sweep: float = field(default=0.0, init=False, repr=False, compare=False)  # angle travelled from start to end in radians, 0 < sweep <= tau
    turn: int = field(default=1, init=False, repr=False, compare=False)  # the direction as a sign: 1 counter-clockwise, -1 clockwise
    box: Box | None = field(default=None, init=False, repr=False, compare=False)  # kept by `chain_index.box_of`

    def __post_init__(self) -> None:
        radius = self.center.distance_to(self.start)
        if radius <= GEOMETRY_TOLERANCE_MM:
            raise ValueError("arc radius must be greater than zero")
        if abs(self.center.distance_to(self.end) - radius) > GEOMETRY_TOLERANCE_MM:
            raise ValueError("arc start and end must be the same distance from the center")
        turn = 1 if self.direction is ArcDirection.CCW else -1
        start_angle = math.atan2(self.start.z - self.center.z, self.start.x - self.center.x)
        end_angle = math.atan2(self.end.z - self.center.z, self.end.x - self.center.x)
        full = self.start.is_close(self.end)
        object.__setattr__(self, "radius", radius)  # one call per field: each has its own type
        object.__setattr__(self, "is_full_circle", full)
        object.__setattr__(self, "start_angle", start_angle)
        object.__setattr__(self, "end_angle", end_angle)
        object.__setattr__(self, "sweep", math.tau if full else ((end_angle - start_angle) * turn) % math.tau)
        object.__setattr__(self, "turn", turn)
        object.__setattr__(self, "box", None)

    @property
    def length(self) -> float:
        return self.radius * self.sweep

    def point_at(self, t: float) -> Point:
        """Point at parameter t (0 = start, 1 = end), exact at both ends."""
        if t == 0:
            return self.start
        if t == 1:
            return self.end
        angle = self.start_angle + self.turn * self.sweep * t
        return Point(
            self.center.x + self.radius * math.cos(angle),
            self.center.z + self.radius * math.sin(angle),
        )

    def __reduce__(self) -> tuple[object, tuple[Point, Point, Point, ArcDirection]]:
        return (ArcSegment, (self.start, self.end, self.center, self.direction))

    def __deepcopy__(self, memo: dict[int, object]) -> ArcSegment:
        return self

    def to_polyline(self, max_deviation_mm: float = ARC_MAX_DEVIATION_MM) -> list[Point]:
        """Points along the arc, start and end included.

        The chords stay inside the circle and never deviate from it by more
        than max_deviation_mm.
        """
        if max_deviation_mm <= 0:
            raise ValueError("max_deviation_mm must be greater than zero")
        ratio = min(1, max_deviation_mm / self.radius)
        step = min(2 * math.acos(1 - ratio), MAX_ARC_SEGMENT_ANGLE_RAD)
        count = max(1, math.ceil(self.sweep / step))
        return [self.point_at(index / count) for index in range(count + 1)]


Segment = LineSegment | ArcSegment


def segments_to_polyline(
    segments: list[Segment], max_deviation_mm: float = ARC_MAX_DEVIATION_MM
) -> list[Point]:
    """Chain segments into one point list; arcs are replaced by chords."""
    points: list[Point] = []
    for segment in segments:
        if isinstance(segment, ArcSegment):
            segment_points = segment.to_polyline(max_deviation_mm)
        else:
            segment_points = [segment.start, segment.end]
        if points and points[-1].is_close(segment_points[0]):
            segment_points = segment_points[1:]
        points.extend(segment_points)
    return points


def polyline_length(points: list[Point]) -> float:
    return sum(a.distance_to(b) for a, b in zip(points, points[1:]))


def signed_area(points: list[Point]) -> float:
    """Area of the closed polygon described by points (closing edge implied).

    Positive if the points run counter-clockwise in the (x, z) plane,
    negative if clockwise.
    """
    total = 0.0
    for current, following in zip(points, points[1:] + points[:1]):
        total += current.x * following.z - following.x * current.z
    return total / 2


def arc_from_endpoints(
    start: Point,
    end: Point,
    radius: float,
    direction: ArcDirection,
    large_arc: bool = False,
) -> ArcSegment:
    """Arc from start to end with a known radius.

    Two circles of that radius pass through both points. The direction picks
    one of them; large_arc selects the arc that sweeps more than half a circle.
    Raises ValueError if the radius is too small for the distance.
    """
    if radius <= GEOMETRY_TOLERANCE_MM:
        raise ValueError("arc radius must be greater than zero")
    chord = start.distance_to(end)
    if chord <= GEOMETRY_TOLERANCE_MM:
        raise ValueError("start and end are the same point; a full circle needs its center")
    half_chord = chord / 2
    if half_chord > radius + GEOMETRY_TOLERANCE_MM:
        raise ValueError("the radius is too small for the distance between start and end")
    height = math.sqrt(max(0, radius**2 - half_chord**2))
    middle = Point((start.x + end.x) / 2, (start.z + end.z) / 2)
    left_normal = Point(-(end.z - start.z) / chord, (end.x - start.x) / chord)
    center_on_left = (direction is ArcDirection.CCW) != large_arc
    side = 1 if center_on_left else -1
    center = Point(
        middle.x + side * left_normal.x * height,
        middle.z + side * left_normal.z * height,
    )
    return ArcSegment(start, end, center, direction)


def _cross(origin: Point, a: Point, b: Point) -> float:
    return (a.x - origin.x) * (b.z - origin.z) - (a.z - origin.z) * (b.x - origin.x)


def _in_box(a: Point, b: Point, p: Point) -> bool:
    tolerance = GEOMETRY_TOLERANCE_MM
    return (
        min(a.x, b.x) - tolerance <= p.x <= max(a.x, b.x) + tolerance
        and min(a.z, b.z) - tolerance <= p.z <= max(a.z, b.z) + tolerance
    )


def segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """True if the straight segments a1-a2 and b1-b2 cross or touch."""
    tolerance_a = GEOMETRY_TOLERANCE_MM * a1.distance_to(a2)
    tolerance_b = GEOMETRY_TOLERANCE_MM * b1.distance_to(b2)
    d1 = _cross(b1, b2, a1)
    d2 = _cross(b1, b2, a2)
    d3 = _cross(a1, a2, b1)
    d4 = _cross(a1, a2, b2)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return (
        (abs(d1) <= tolerance_b and _in_box(b1, b2, a1))
        or (abs(d2) <= tolerance_b and _in_box(b1, b2, a2))
        or (abs(d3) <= tolerance_a and _in_box(a1, a2, b1))
        or (abs(d4) <= tolerance_a and _in_box(a1, a2, b2))
    )
