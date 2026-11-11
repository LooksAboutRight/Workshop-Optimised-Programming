"""What a dimension looks like in the picture, worked out in sketch coordinates (x = radius, z = axial), without a toolkit.

A dimension has extension lines from what it measures to its dimension line, the dimension line with an arrow at each
end, and its number. Where the line goes is the `place` (the mouse position while placing, later the stored offset from
the middle of what is measured). `placement_kind` decides from that place whether a distance is the true length, the
distance along Z or the distance along X.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.geometry import Point

ANGLE_STEPS = 24  # pieces of the arc that shows an angle

KIND_LENGTH = "length"
KIND_ALONG_Z = "along_z"
KIND_ALONG_X = "along_x"


@dataclass(frozen=True)
class DimensionGraphic:
    lines: tuple[tuple[Point, Point], ...] = ()  # extension lines and the dimension line
    arrows: tuple[tuple[Point, Point], ...] = ()  # (tip, a point behind it): the arrow points from the second to the first
    curve: tuple[Point, ...] = ()  # an arc (angles)
    text_at: Point = Point(0, 0)


def placement_kind(p: Point, q: Point, mouse: Point, near: float) -> str:
    """Length when the mouse is next to the line p-q (within `near`), the distance along X when it is to the side of it,
    the distance along Z when it is above or below it; inside the box round it but not near the line: the length."""
    dx, dz = q.x - p.x, q.z - p.z
    length_squared = dx * dx + dz * dz
    if length_squared > 0:
        along = ((mouse.x - p.x) * dx + (mouse.z - p.z) * dz) / length_squared
        across = abs((mouse.x - p.x) * dz - (mouse.z - p.z) * dx) / math.sqrt(length_squared)
        if 0 <= along <= 1 and across <= near:
            return KIND_LENGTH
    low_z, high_z = sorted((p.z, q.z))
    low_x, high_x = sorted((p.x, q.x))
    beside = max(low_z - mouse.z, mouse.z - high_z, 0)  # how far the mouse is out to the side of the span in z
    above = max(low_x - mouse.x, mouse.x - high_x, 0)  # and above or below it in x
    if beside > above:
        return KIND_ALONG_X
    if above > beside:
        return KIND_ALONG_Z
    return KIND_LENGTH


def _unit(dx: float, dz: float) -> tuple[float, float]:
    length = math.hypot(dx, dz)
    return (1.0, 0.0) if length == 0 else (dx / length, dz / length)


def _spanning(p: Point, q: Point, a: Point, b: Point) -> DimensionGraphic:
    """Extension lines p-a and q-b and the dimension line a-b with its arrows."""
    return DimensionGraphic(((p, a), (q, b), (a, b)), ((a, b), (b, a)), (), Point((a.x + b.x) / 2, (a.z + b.z) / 2))


def _point(value) -> Point:
    return Point(value[0], value[1])


def graphic(kind: str, args: list, place: Point, values: tuple[float, ...] = ()) -> DimensionGraphic:
    """The drawing of a dimension of this kind. `args` are the geometry its relation sees (see Sketch.constraint_args);
    `values` are its values (an angle needs its flips to know which of the four angles it shows)."""
    if kind == "distance_z":
        p, q = _point(args[0]), _point(args[1])
        return _spanning(p, q, Point(place.x, p.z), Point(place.x, q.z))
    if kind == "distance_x":
        p, q = _point(args[0]), _point(args[1])
        return _spanning(p, q, Point(p.x, place.z), Point(q.x, place.z))
    if kind in ("distance", "length"):
        p, q = (_point(args[0]), _point(args[1])) if kind == "distance" else (_point(args[0][0]), _point(args[0][1]))
        ux, uz = _unit(q.x - p.x, q.z - p.z)
        nx, nz = -uz, ux
        side = (place.x - p.x) * nx + (place.z - p.z) * nz
        return _spanning(p, q, Point(p.x + nx * side, p.z + nz * side), Point(q.x + nx * side, q.z + nz * side))
    if kind == "distance_line":  # the radius to a centre line: extension lines along the centre line, the dimension line square to it
        p, (c0, c1) = _point(args[0]), (_point(args[1][0]), _point(args[1][1]))
        ux, uz = _unit(c1.x - c0.x, c1.z - c0.z)
        reach = (p.x - c0.x) * ux + (p.z - c0.z) * uz
        foot = Point(c0.x + ux * reach, c0.z + uz * reach)
        shift = (place.x - p.x) * ux + (place.z - p.z) * uz
        return _spanning(p, foot, Point(p.x + ux * shift, p.z + uz * shift), Point(foot.x + ux * shift, foot.z + uz * shift))
    if kind in ("radius", "diameter"):
        return _round(kind, args[0], place)
    if kind == "angle":
        return _angle(args, place, values)
    return DimensionGraphic(text_at=place)


def _round(kind: str, arc, place: Point) -> DimensionGraphic:
    centre, start = _point(arc[0]), _point(arc[1])
    radius = centre.distance_to(start)
    vx, vz = _unit(place.x - centre.x, place.z - centre.z)
    tip = Point(centre.x + vx * radius, centre.z + vz * radius)
    outside = centre.distance_to(place) > radius
    behind = place if outside else centre  # the arrow comes from outside the circle, or from its middle
    if kind == "radius":
        end = place if outside else tip
        return DimensionGraphic(((centre, end),), ((tip, behind),), (), place)
    opposite = Point(centre.x - vx * radius, centre.z - vz * radius)
    end = place if outside else tip
    return DimensionGraphic(((opposite, end),), ((tip, opposite), (opposite, tip)), (), place)


def _vertex(args: list) -> tuple[Point, tuple[float, float], tuple[float, float]] | None:
    """Where the two lines cross and the unit direction of each (None: they are parallel)."""
    (a0, a1), (b0, b1) = ([_point(p) for p in line] for line in args)
    da, db = _unit(a1.x - a0.x, a1.z - a0.z), _unit(b1.x - b0.x, b1.z - b0.z)
    denominator = da[0] * db[1] - da[1] * db[0]
    if denominator == 0:
        return None
    t = ((b0.x - a0.x) * db[1] - (b0.z - a0.z) * db[0]) / denominator
    return Point(a0.x + da[0] * t, a0.z + da[1] * t), da, db


def sector_flips(args: list, place: Point) -> tuple[float, float]:
    """Which of the four angles between two lines the place is in: the flip (1 or -1) of each line's ray."""
    found = _vertex(args)
    if found is None:
        return 1, 1
    vertex, da, db = found
    mx, mz = place.x - vertex.x, place.z - vertex.z
    denominator = da[0] * db[1] - da[1] * db[0]
    along_a = (mx * db[1] - mz * db[0]) / denominator  # place = along_a * da + along_b * db
    along_b = (da[0] * mz - da[1] * mx) / denominator
    return (1 if along_a >= 0 else -1), (1 if along_b >= 0 else -1)


def _extension(vertex: Point, ray: tuple[float, float], ends: list[Point], reach: float) -> list[tuple[Point, Point]]:
    """Lines that carry a line out to the vertex and out to the arc, where the line itself does not reach."""
    along = [(p.x - vertex.x) * ray[0] + (p.z - vertex.z) * ray[1] for p in ends]
    low, high = min(along), max(along)
    if high <= 0:  # the line is all on the other side of the vertex: the whole ray is an extension
        return [(vertex, Point(vertex.x + ray[0] * reach, vertex.z + ray[1] * reach))]
    pieces = []
    if low > 0:
        pieces.append((vertex, Point(vertex.x + ray[0] * low, vertex.z + ray[1] * low)))
    if reach > high:
        pieces.append((Point(vertex.x + ray[0] * high, vertex.z + ray[1] * high), Point(vertex.x + ray[0] * reach, vertex.z + ray[1] * reach)))
    return pieces


def _angle(args: list, place: Point, values: tuple[float, ...]) -> DimensionGraphic:
    found = _vertex(args)
    radius = 0 if found is None else found[0].distance_to(place)
    if found is None or radius == 0:  # parallel lines have no angle to draw, only the number
        return DimensionGraphic(text_at=place)
    vertex, da, db = found
    flip_a = values[1] if len(values) > 1 else 1
    flip_b = values[2] if len(values) > 2 else 1
    ray_a, ray_b = (da[0] * flip_a, da[1] * flip_a), (db[0] * flip_b, db[1] * flip_b)
    sweep = math.atan2(ray_a[0] * ray_b[1] - ray_a[1] * ray_b[0], ray_a[0] * ray_b[0] + ray_a[1] * ray_b[1])

    def turned(fraction: float) -> Point:
        c, s = math.cos(sweep * fraction), math.sin(sweep * fraction)
        return Point(vertex.x + radius * (ray_a[0] * c - ray_a[1] * s), vertex.z + radius * (ray_a[0] * s + ray_a[1] * c))

    curve = tuple(turned(i / ANGLE_STEPS) for i in range(ANGLE_STEPS + 1))
    lines = []
    for ray, line in zip((ray_a, ray_b), args):
        lines += _extension(vertex, ray, [_point(p) for p in line], radius)
    return DimensionGraphic(tuple(lines), ((curve[0], curve[1]), (curve[-1], curve[-2])), curve, turned(1 / 2))
