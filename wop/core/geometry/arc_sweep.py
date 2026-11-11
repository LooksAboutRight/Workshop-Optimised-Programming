"""The region a tool edge sweeps when the tool moves along a circular arc (no rotation): exact, with arcs and lines only.

A point `q` of the tool at the start of the move is at `q + D + R u(t)` when the tool tip is at the angle `t` of the path arc (`D` is the
path centre minus the start of the path, `R` its radius, `u(t) = (cos t, sin t)`). So every point of the sweep of an edge is a
sum of two such terms, and the boundary is made of arcs whose centres and radii are known:
  - a line edge `a b` (parameter `s` from 0 to 1): the sweep is `a + s (b - a) + D + R u(t)`. The ends of the edge trace arcs of radius
    R, the edge at the start and at the end of the move are lines. The map folds where the path tangent is parallel to the edge: the
    path is cut there, and each piece is a loop of two arcs and two lines.
  - an arc edge (centre `c`, radius `r`, angle `p`): the sweep is `c + D + r u(p) + R u(t)`. The ends of the edge trace arcs of radius R, the edge at the
    start and the end of the move are arcs of radius r, and where the tangents are parallel (`p - t` a multiple of a half turn) the map folds: the
    envelope there is an arc around `c + D` of radius R + r (a whole turn apart) or |R - r| (a half turn apart). The rectangle of (p, t) is cut along
    those lines into triangles and quadrilaterals; the border of each is a loop of such arcs.
The pieces may overlap (the sweep is their union): subtracting them one after the other from the material gives the same.
"""

from __future__ import annotations

import math

from ..constants import GEOMETRY_TOLERANCE_MM
from .primitives import ArcDirection, ArcSegment, LineSegment, Point, Segment
from .chains import Loop, closed_loop, oriented

Vertex = tuple[float, float]  # (angle on the edge, angle on the path)


def _u(angle: float) -> tuple[float, float]:
    return math.cos(angle), math.sin(angle)


def ccw_range(arc: ArcSegment) -> tuple[float, float]:
    """The angles (a0 < a1 <= a0 + a whole turn) the arc covers, whatever its direction of travel."""
    if arc.direction is ArcDirection.CCW:
        return arc.start_angle, arc.start_angle + arc.sweep
    return arc.end_angle, arc.end_angle + arc.sweep


def arc_at(center: Point, radius: float, start: float, end: float) -> ArcSegment | None:
    """The arc around `center` from the angle `start` to the angle `end` (counter-clockwise when `end` is larger)."""
    if radius <= GEOMETRY_TOLERANCE_MM or abs(end - start) <= GEOMETRY_TOLERANCE_MM:
        return None
    ux, uz = _u(start)
    vx, vz = _u(end)
    first = Point(center.x + radius * ux, center.z + radius * uz)
    last = Point(center.x + radius * vx, center.z + radius * vz)
    return ArcSegment(first, last, center, ArcDirection.CCW if end > start else ArcDirection.CW)


def point_at(center: Point, radius: float, angle: float) -> Point:
    ux, uz = _u(angle)
    return Point(center.x + radius * ux, center.z + radius * uz)


def _joined(pieces: list[Segment | None]) -> Loop | None:
    """The pieces in order, the missing ones (a zero radius) left out; None when nothing is left or they do not close."""
    ring = [piece for piece in pieces if piece is not None and (isinstance(piece, ArcSegment) or piece.length > GEOMETRY_TOLERANCE_MM)]
    if len(ring) < 2:
        return None
    try:
        return oriented(closed_loop(ring), True)
    except ValueError:
        return None


# --- a line edge along an arc ------------------------------------------------------------------

def line_along_arc(a: Point, b: Point, path: ArcSegment) -> list[Loop]:
    """The sweep of the line edge `a b` (placed at the start of the move) along the arc `path`, as loops."""
    ex, ez = b.x - a.x, b.z - a.z
    start, end = ccw_range(path)
    base = path.start  # the tool tip starts here: the offset of a tool point is D = the centre of the path - the start of the path
    dx, dz = path.center.x - base.x, path.center.z - base.z
    folds = []
    fold = math.atan2(-ex, ez)  # the angle where the path tangent is parallel to the edge, and a half turn further
    for candidate in (fold, fold + math.pi):
        k = math.ceil((start - candidate) / (2 * math.pi))
        angle = candidate + k * 2 * math.pi
        while angle < end:
            if angle > start + GEOMETRY_TOLERANCE_MM and angle < end - GEOMETRY_TOLERANCE_MM:
                folds.append(angle)
            angle += 2 * math.pi
    cuts = [start, *sorted(folds), end]
    loops: list[Loop] = []
    for t0, t1 in zip(cuts, cuts[1:]):
        a_centre, b_centre = Point(a.x + dx, a.z + dz), Point(b.x + dx, b.z + dz)
        p_a0, p_b0 = point_at(a_centre, path.radius, t0), point_at(b_centre, path.radius, t0)
        p_a1, p_b1 = point_at(a_centre, path.radius, t1), point_at(b_centre, path.radius, t1)
        ring = [
            LineSegment(p_a0, p_b0),
            arc_at(b_centre, path.radius, t0, t1),
            LineSegment(p_b1, p_a1),
            arc_at(a_centre, path.radius, t1, t0),
        ]
        loop = _joined(ring)
        if loop is not None:
            loops.append(loop)
    return loops


# --- an arc edge along an arc ------------------------------------------------------------------

def _split(polygon: list[Vertex], level: float) -> tuple[list[Vertex], list[Vertex]]:
    """A convex polygon of (p, t) cut by the line p - t = level: the part where p - t >= level and the part where it is <= level."""
    above: list[Vertex] = []
    below: list[Vertex] = []
    for index, here in enumerate(polygon):
        there = polygon[(index + 1) % len(polygon)]
        d_here, d_there = here[0] - here[1] - level, there[0] - there[1] - level
        if d_here >= -GEOMETRY_TOLERANCE_MM:
            above.append(here)
        if d_here <= GEOMETRY_TOLERANCE_MM:
            below.append(here)
        if (d_here > GEOMETRY_TOLERANCE_MM and d_there < -GEOMETRY_TOLERANCE_MM) or (d_here < -GEOMETRY_TOLERANCE_MM and d_there > GEOMETRY_TOLERANCE_MM):
            share = d_here / (d_here - d_there)
            cut = (here[0] + share * (there[0] - here[0]), here[1] + share * (there[1] - here[1]))
            above.append(cut)
            below.append(cut)
    return above, below


def _area(polygon: list[Vertex]) -> float:
    return sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(polygon, polygon[1:] + polygon[:1])) / 2


def arc_along_arc(edge: ArcSegment, path: ArcSegment) -> list[Loop]:
    """The sweep of the arc edge `edge` (placed at the start of the move) along the arc `path`, as loops (see the top of the file)."""
    r, big = edge.radius, path.radius
    p0, p1 = ccw_range(edge)
    t0, t1 = ccw_range(path)
    base = path.start
    centre = Point(edge.center.x + path.center.x - base.x, edge.center.z + path.center.z - base.z)  # c + D

    pieces: list[list[Vertex]] = [[(p0, t0), (p1, t0), (p1, t1), (p0, t1)]]
    low, high = p0 - t1, p1 - t0
    for k in range(math.ceil(low / math.pi - GEOMETRY_TOLERANCE_MM), math.floor(high / math.pi + GEOMETRY_TOLERANCE_MM) + 1):
        level = k * math.pi
        cut: list[list[Vertex]] = []
        for polygon in pieces:
            for part in _split(polygon, level):
                if len(part) > 2 and abs(_area(part)) > GEOMETRY_TOLERANCE_MM:
                    cut.append(part)
        pieces = cut
    loops: list[Loop] = []
    for polygon in pieces:
        ring: list[Segment | None] = []
        for index, (p, t) in enumerate(polygon):
            q, s = polygon[(index + 1) % len(polygon)]
            if abs(p - q) <= GEOMETRY_TOLERANCE_MM:  # the end of the edge at angle p traces an arc of radius R
                ring.append(arc_at(point_at(centre, r, p), big, t, s))
            elif abs(t - s) <= GEOMETRY_TOLERANCE_MM:  # the edge itself, at the angle t of the path
                ring.append(arc_at(point_at(centre, big, t), r, p, q))
            else:  # along p - t = k half turns: the envelope, an arc around the centre
                k = round((p - t) / math.pi)
                signed = big + (-1) ** k * r
                ring.append(arc_at(centre, abs(signed), t if signed >= 0 else t + math.pi, s if signed >= 0 else s + math.pi))
        loop = _joined(ring)
        if loop is not None:
            loops.append(loop)
    return loops
