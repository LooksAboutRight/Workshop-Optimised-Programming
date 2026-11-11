"""Relations and dimensions of a sketch: what each kind demands, written as equations that are zero when it holds.

A `Constraint` is stored in the sketch: a kind, the ids it refers to (points, lines or arcs, as the kind says) and, for a
dimension, its values. The kind's `Relation` turns the geometry of those ids into residuals; the solver
(`solver.py`) moves the points until they are all zero. Angles are radians inside, degrees on the screen.
A line is its two points (start, end), an arc is (centre, start, end); a circle is an arc whose start is its end.
x is the radius and z the axial position: "horizontal" is as seen in the picture, z to the right, x up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import LENGTH_FLOOR, SLOT_ARC, SLOT_LINE, SLOT_POINT

Vector = tuple[float, float]  # (x, z)


@dataclass(frozen=True)
class Constraint:
    constraint_id: int
    kind: str
    refs: tuple[int, ...]
    values: tuple[float, ...] = ()
    offset: tuple[float, float] | None = None  # a dimension: where its line was placed, (x, z) from the middle of what it measures


def _sub(a: Vector, b: Vector) -> Vector:
    return a[0] - b[0], a[1] - b[1]


def _dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Vector, b: Vector) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _norm(a: Vector) -> float:
    return math.hypot(a[0], a[1])


def _unit_product(a: Vector, b: Vector) -> float:
    return max(_norm(a) * _norm(b), LENGTH_FLOOR)


def _wrap(angle: float) -> float:
    return (angle + math.pi) % math.tau - math.pi


def _radius(arc) -> float:
    return _norm(_sub(arc[1], arc[0]))


class Relation:
    """One kind of relation. `slots` says what each ref is; the arguments of `equations` follow the slots:
    a point is (x, z), a line is (start, end), an arc is (centre, start, end)."""

    kind = ""
    label = ""
    slots: tuple[str, ...] = ()
    dimension = False
    unit = ""  # "mm" or "deg" for a dimension

    def equations(self, args: list, values: tuple[float, ...]) -> list[float]:
        raise NotImplementedError

    def measure(self, args: list) -> tuple[float, ...]:
        """The values the geometry has now (the first value of a new dimension)."""
        return ()

    def valid(self, refs: tuple[int, ...]) -> bool:
        return True

    def to_display(self, value: float) -> float:
        return value

    def from_display(self, shown: float) -> float:
        return shown

    def anchor(self, args: list) -> Vector:
        """Where the tag of this relation is drawn."""
        points = [p for a in args for p in (a if isinstance(a[0], tuple) else (a,))]
        return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


class _TwoPoints(Relation):
    slots = (SLOT_POINT, SLOT_POINT)

    def valid(self, refs: tuple[int, ...]) -> bool:
        return refs[0] != refs[1]


class Horizontal(_TwoPoints):
    kind, label = "horizontal", "Horizontal"

    def equations(self, args, values):
        return [args[0][0] - args[1][0]]


class Vertical(_TwoPoints):
    kind, label = "vertical", "Vertical"

    def equations(self, args, values):
        return [args[0][1] - args[1][1]]


class Fixed(Relation):
    kind, label, slots = "fixed", "Fixed", (SLOT_POINT,)

    def equations(self, args, values):
        return [args[0][0] - values[0], args[0][1] - values[1]]

    def measure(self, args):
        return args[0]


class Parallel(Relation):
    kind, label, slots = "parallel", "Parallel", (SLOT_LINE, SLOT_LINE)

    def equations(self, args, values):
        a, b = _sub(args[0][1], args[0][0]), _sub(args[1][1], args[1][0])
        return [_cross(a, b) / _unit_product(a, b)]

    def valid(self, refs):
        return refs[0] != refs[1]


class Perpendicular(Parallel):
    kind, label = "perpendicular", "Perpendicular"

    def equations(self, args, values):
        a, b = _sub(args[0][1], args[0][0]), _sub(args[1][1], args[1][0])
        return [_dot(a, b) / _unit_product(a, b)]


class EqualLength(Parallel):
    kind, label = "equal_length", "Equal length"

    def equations(self, args, values):
        return [_norm(_sub(args[0][1], args[0][0])) - _norm(_sub(args[1][1], args[1][0]))]


class EqualRadius(Parallel):
    kind, label, slots = "equal_radius", "Equal radius", (SLOT_ARC, SLOT_ARC)

    def equations(self, args, values):
        return [_radius(args[0]) - _radius(args[1])]


class TangentLineArc(Relation):
    """The line meets the arc at the third ref (a point of both); the line is square to the radius there."""

    kind, label, slots = "tangent_line_arc", "Tangent", (SLOT_LINE, SLOT_ARC, SLOT_POINT)

    def equations(self, args, values):
        line, arc, touch = args
        radius_direction, line_direction = _sub(touch, arc[0]), _sub(line[1], line[0])
        return [_dot(radius_direction, line_direction) / _unit_product(radius_direction, line_direction)]


class TangentArcs(Relation):
    """Two arcs meet at the third ref; the two centres and that point are on one line."""

    kind, label, slots = "tangent_arcs", "Tangent", (SLOT_ARC, SLOT_ARC, SLOT_POINT)

    def equations(self, args, values):
        first, second, touch = args
        a, b = _sub(touch, first[0]), _sub(touch, second[0])
        return [_cross(a, b) / _unit_product(a, b)]


class PointOnLine(Relation):
    kind, label, slots = "point_on_line", "Point on line", (SLOT_POINT, SLOT_LINE)

    def equations(self, args, values):
        point, line = args
        along = _sub(line[1], line[0])
        return [_cross(along, _sub(point, line[0])) / max(_norm(along), LENGTH_FLOOR)]


class PointOnCircle(Relation):
    kind, label, slots = "point_on_circle", "Point on arc / circle", (SLOT_POINT, SLOT_ARC)

    def equations(self, args, values):
        point, arc = args
        return [_norm(_sub(point, arc[0])) - _radius(arc)]


class Midpoint(Relation):
    kind, label, slots = "midpoint", "Midpoint", (SLOT_POINT, SLOT_LINE)

    def equations(self, args, values):
        point, line = args
        return [point[0] - (line[0][0] + line[1][0]) / 2, point[1] - (line[0][1] + line[1][1]) / 2]


class Symmetric(Relation):
    """The two points are mirror images of each other about the line."""

    kind, label, slots = "symmetric", "Symmetric about line", (SLOT_POINT, SLOT_POINT, SLOT_LINE)

    def equations(self, args, values):
        first, second, (a, b) = args
        along = _sub(b, a)
        length = max(_norm(along), LENGTH_FLOOR)
        middle = ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)
        return [_cross(along, _sub(middle, a)) / length, _dot(along, _sub(second, first)) / length]

    def valid(self, refs):
        return refs[0] != refs[1]


class SymmetricAxisZ(_TwoPoints):
    """Mirror images about the Z axis (the spindle axis, x = 0)."""

    kind, label = "symmetric_axis_z", "Symmetric about the Z axis"

    def equations(self, args, values):
        return [args[0][0] + args[1][0], args[0][1] - args[1][1]]


class SymmetricAxisX(_TwoPoints):
    """Mirror images about the X axis (the line z = 0)."""

    kind, label = "symmetric_axis_x", "Symmetric about the X axis"

    def equations(self, args, values):
        return [args[0][1] + args[1][1], args[0][0] - args[1][0]]


class _Dimension(Relation):
    dimension = True
    unit = "mm"


class Distance(_Dimension, _TwoPoints):
    kind, label = "distance", "Distance"

    def equations(self, args, values):
        return [_norm(_sub(args[1], args[0])) - values[0]]

    def measure(self, args):
        return (_norm(_sub(args[1], args[0])),)


class DistanceZ(_Dimension, _TwoPoints):
    """Signed: second point minus first point, along z."""

    kind, label = "distance_z", "Distance along Z"

    def equations(self, args, values):
        return [args[1][1] - args[0][1] - values[0]]

    def measure(self, args):
        return (args[1][1] - args[0][1],)


class DistanceX(DistanceZ):
    kind, label = "distance_x", "Distance along X (radius)"

    def equations(self, args, values):
        return [args[1][0] - args[0][0] - values[0]]

    def measure(self, args):
        return (args[1][0] - args[0][0],)


class DistanceLine(_Dimension):
    """The distance from a point to a line (square to it): the radius to a centre line, whatever the centre line is. The spindle
    axis is a line like any other here (`AXIS_LINE`)."""

    kind, label, slots = "distance_line", "Distance to a line (the radius to a centre line)", (SLOT_POINT, SLOT_LINE)

    @staticmethod
    def _distance(args) -> float:
        point, (start, end) = args
        along = _sub(end, start)
        return abs(_cross(along, _sub(point, start))) / max(_norm(along), LENGTH_FLOOR)

    def equations(self, args, values):
        return [self._distance(args) - values[0]]

    def measure(self, args):
        return (self._distance(args),)

    def anchor(self, args):
        """Halfway between the point and its foot on the line."""
        point, (start, end) = args
        along = _sub(end, start)
        reach = _dot(_sub(point, start), along) / max(_dot(along, along), LENGTH_FLOOR)
        foot = (start[0] + along[0] * reach, start[1] + along[1] * reach)
        return (point[0] + foot[0]) / 2, (point[1] + foot[1]) / 2


class Length(_Dimension):
    kind, label, slots = "length", "Length", (SLOT_LINE,)

    def equations(self, args, values):
        return [_norm(_sub(args[0][1], args[0][0])) - values[0]]

    def measure(self, args):
        return (_norm(_sub(args[0][1], args[0][0])),)


class Radius(_Dimension):
    kind, label, slots = "radius", "Radius", (SLOT_ARC,)

    def equations(self, args, values):
        return [_radius(args[0]) - values[0]]

    def measure(self, args):
        return (_radius(args[0]),)


class Diameter(Radius):
    kind, label = "diameter", "Diameter"

    def equations(self, args, values):
        return [_radius(args[0]) - values[0] / 2]

    def measure(self, args):
        return (2 * _radius(args[0]),)


class _AngleDimension(Relation):
    dimension = True
    unit = "deg"

    def to_display(self, value: float) -> float:
        return math.degrees(value)

    def from_display(self, shown: float) -> float:
        return math.radians(shown)


class Angle(_AngleDimension):
    """The angle from a ray of the first line to a ray of the second (counter-clockwise in the (x, z) plane).

    Two crossing lines have four angles. `values` is (angle, flip of the first line, flip of the second): a flip of -1
    takes the ray that runs against the direction the line was drawn in, so the dimension can be any of the four.
    Without the flips (1) both rays follow the lines.
    """

    kind, label, slots = "angle", "Angle between lines", (SLOT_LINE, SLOT_LINE)

    @staticmethod
    def rays(args, values) -> tuple[Vector, Vector]:
        flip_a = values[1] if len(values) > 1 else 1
        flip_b = values[2] if len(values) > 2 else 1
        a, b = _sub(args[0][1], args[0][0]), _sub(args[1][1], args[1][0])
        return (a[0] * flip_a, a[1] * flip_a), (b[0] * flip_b, b[1] * flip_b)

    def equations(self, args, values):
        a, b = self.rays(args, values)
        return [_wrap(math.atan2(_cross(a, b), _dot(a, b)) - values[0])]

    def measure(self, args, values=()):
        a, b = self.rays(args, values)
        return (math.atan2(_cross(a, b), _dot(a, b)),)

    def valid(self, refs):
        return refs[0] != refs[1]


class AngleZ(_AngleDimension):
    """The angle of a line from the +z direction towards +x, as seen in the picture (the convention of the contour editor)."""

    kind, label, slots = "angle_z", "Angle to Z axis", (SLOT_LINE,)

    def equations(self, args, values):
        along = _sub(args[0][1], args[0][0])
        return [_wrap(math.atan2(along[0], along[1]) - values[0])]

    def measure(self, args):
        along = _sub(args[0][1], args[0][0])
        return (math.atan2(along[0], along[1]),)


RELATIONS = (
    Horizontal(), Vertical(), Fixed(), Parallel(), Perpendicular(), EqualLength(), EqualRadius(), TangentLineArc(),
    TangentArcs(), PointOnLine(), PointOnCircle(), Midpoint(), Symmetric(), SymmetricAxisZ(), SymmetricAxisX(),
    Distance(), DistanceZ(), DistanceX(), DistanceLine(), Length(), Radius(), Diameter(), Angle(), AngleZ(),
)


def relation_for(kind: str) -> Relation:
    for relation in RELATIONS:
        if relation.kind == kind:
            return relation
    raise KeyError(f"unknown relation {kind!r}")
