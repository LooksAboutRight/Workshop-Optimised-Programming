"""The reference point of a tool: where it is touched off, and the point whose path the program describes.

At the machine a tool is touched off on a turned diameter (X) and on a faced end (Z). That measures the lowest X
and the lowest Z of the cutting edges (for a boring bar the highest X, for a left-hand tool the highest Z), which
is the corner of the box around the cutting edges in the cutting direction. For a tool with a corner of 90 degrees
that is the sharp corner, for other inserts it is a point that is not on the tool at all. This corner, not the
sharp corner of the two edge lines, is the default reference point.

If one coordinate of that corner would lie at the far end of a cutting edge (an edge that leans forward over the work:
the side edge angle of a turning tool below 90 degrees, the wall edge of a boring bar leaning towards the wall), the
corner is not on the tool: that coordinate is then taken at the point that gives the other one, the point under the
nose radius (under the sharp corner without a nose radius). If both would, the nearest point of the cutting edges counts.

A tool that is symmetric in Z (a threading tool) is touched off at its lowest X point, in the middle of its tip.
Any other choice is a named point `tip` drawn in the tool shape editor; it replaces the computed one.

Tools are stored in the coordinates they were drawn in. `with_tip_at_origin` moves the whole tool so that the
reference point is the origin: the checks, the pictures and the block planners use that tool.
"""

from __future__ import annotations

import math
from dataclasses import replace
from functools import cache

from ..constants import ARC_MAX_DEVIATION_MM, GEOMETRY_TOLERANCE_MM, TIP_DIRECTION_TOLERANCE_MM, TIP_POINT
from ..geometry import ArcSegment, LineSegment, Point, Segment, segments_to_polyline
from .tool import Tool, ToolSegment, ToolSegmentRole, ToolShape


AXIS_ANGLES = (0, math.pi / 2, math.pi, -math.pi / 2)  # the directions of +X, +Z, -X, -Z seen from the centre of an arc


def arc_extremes(arc: ArcSegment) -> list[Point]:
    """The points of an arc that lie furthest in X or in Z: the polyline of an arc misses them by a hair, and the
    reference point of a tool must be exact."""
    found = []
    for angle in AXIS_ANGLES:
        travelled = ((angle - arc.start_angle) * arc.direction.value) % math.tau
        if arc.is_full_circle or travelled <= arc.sweep + GEOMETRY_TOLERANCE_MM:
            found.append(Point(arc.center.x + arc.radius * math.cos(angle), arc.center.z + arc.radius * math.sin(angle)))
    return found


def _outline_points(segments) -> list[Point]:
    points = segments_to_polyline(list(segments), ARC_MAX_DEVIATION_MM)
    for segment in segments:
        if isinstance(segment, ArcSegment):
            points += arc_extremes(segment)
    return points


@cache
def _default_tip(shape: ToolShape) -> Point:
    outline = [point for segment in shape.segments for point in _outline_points([segment])]
    mean_x = sum(point.x for point in outline) / len(outline)
    mean_z = sum(point.z for point in outline) / len(outline)
    cutter = [point for segment in shape.cutter_segments for point in _outline_points([segment])]
    if not cutter:
        return Point(0, 0)
    towards_axis = min if mean_x >= 0 else max  # the lowest X of an outside tool, the highest of a boring bar
    x = towards_axis(point.x for point in cutter)  # the body lies behind the tip: towards larger X for an outside tool
    if abs(mean_z) <= TIP_DIRECTION_TOLERANCE_MM:  # symmetric in Z: the middle of the lowest (highest) point
        lowest = [point.z for point in cutter if abs(point.x - x) <= GEOMETRY_TOLERANCE_MM]
        return Point(x, sum(lowest) / len(lowest))
    towards_chuck = min if mean_z >= 0 else max  # the lowest Z of a right-hand tool, the highest of a left-hand tool
    z = towards_chuck(point.z for point in cutter)
    ends = _chain_ends(shape)

    def only_at_ends(axis: str, value: float) -> bool:
        reached = [point for point in cutter if abs(getattr(point, axis) - value) <= TIP_DIRECTION_TOLERANCE_MM]
        return all(any(point.is_close(end, TIP_DIRECTION_TOLERANCE_MM) for end in ends) for point in reached)

    x_off, z_off = only_at_ends("x", x), only_at_ends("z", z)
    # An edge that leans so far forward that the box corner would lie at its far end, away from the nose, puts the
    # corner in the air. That coordinate is then taken at the point that gives the other one (the point under the nose
    # radius); X stays the point the tool touches in X, Z the point it touches in Z.
    if x_off and z_off:  # both edges lean forward: the point of the cutting edges nearest to the box corner
        return min(cutter, key=lambda point: point.distance_to(Point(x, z)))
    if z_off:
        z = towards_chuck(point.z for point in cutter if abs(point.x - x) <= TIP_DIRECTION_TOLERANCE_MM)
    elif x_off:
        x = towards_axis(point.x for point in cutter if abs(point.z - z) <= TIP_DIRECTION_TOLERANCE_MM)
    return Point(x, z)


def _chain_ends(shape: ToolShape) -> list[Point]:
    """The two ends of every run of cutting pieces (a point where a cutting piece meets a holder piece)."""
    pieces = shape.pieces
    ends: list[Point] = []
    for index, piece in enumerate(pieces):
        if piece.role is not ToolSegmentRole.CUTTER:
            continue
        if pieces[index - 1].role is not ToolSegmentRole.CUTTER:
            ends.append(piece.segment.start)
        if pieces[(index + 1) % len(pieces)].role is not ToolSegmentRole.CUTTER:
            ends.append(piece.segment.end)
    return ends


def default_tip(shape: ToolShape) -> Point:
    """The touch-off point worked out from the cutting edges of the shape (see the top of this file)."""
    return _default_tip(shape)


def tip_of(tool: Tool) -> Point:
    """The reference point of the tool in its own (drawn) coordinates: the named point `tip`, else the computed one."""
    for point in tool.points:
        if point.name.casefold() == TIP_POINT.casefold():
            return point.position
    return default_tip(tool.shape)


def tip_is_drawn(tool: Tool) -> bool:
    """True when the tool carries its own named point `tip` (the computed one is not used)."""
    return any(point.name.casefold() == TIP_POINT.casefold() for point in tool.points)


def _moved(segment: Segment, dx: float, dz: float) -> Segment:
    def shift(point: Point) -> Point:
        return Point(point.x + dx, point.z + dz)

    if isinstance(segment, ArcSegment):
        return ArcSegment(shift(segment.start), shift(segment.end), shift(segment.center), segment.direction)
    return LineSegment(shift(segment.start), shift(segment.end))


def with_tip_at_origin(tool: Tool) -> Tool:
    """The tool moved so that its reference point is (0, 0); the named points move with it."""
    tip = tip_of(tool)
    if tip.distance_to(Point(0, 0)) <= GEOMETRY_TOLERANCE_MM:
        return tool
    dx, dz = -tip.x, -tip.z
    pieces = tuple(ToolSegment(_moved(piece.segment, dx, dz), piece.role) for piece in tool.shape.pieces)
    points = tuple(replace(point, x=point.x + dx, z=point.z + dz) for point in tool.points)
    return replace(tool, shape=ToolShape(pieces), points=points)


def nose_circle(tool: Tool) -> tuple[float, Point]:
    """The nose radius of the tool and the centre of that arc, in the coordinates of the tool with its tip at the
    origin: (0, origin) for a sharp tool. With several arcs on the cutting edge the smallest one, the one nearest
    to the origin, counts."""
    arcs = [segment for segment in tool.shape.cutter_segments if isinstance(segment, ArcSegment)]
    if not arcs:
        return 0, Point(0, 0)
    radius = min(arc.center.distance_to(arc.start) for arc in arcs)
    nose = [arc for arc in arcs if math.isclose(arc.center.distance_to(arc.start), radius, abs_tol=GEOMETRY_TOLERANCE_MM)]
    best = min(nose, key=lambda arc: arc.center.distance_to(Point(0, 0)))
    return radius, best.center
