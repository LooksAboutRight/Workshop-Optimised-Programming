"""The curves along which the tool tip stays in touch with the part: the boundary of the places where the tool may stand.

The tip is at `T`. The tool touches a piece of the part when a point of a tool edge lies on the piece and the two do not cross. Every touch is
one of a few kinds, and each kind is a curve of `T`, known exactly (lines and arcs, no samples):
  - a corner of the tool on the piece: the piece moved by minus the corner;
  - a corner of the piece on an edge of the tool: the edge turned a half turn (point mirrored) and moved to the corner;
  - an arc of the tool tangent to a line of the piece: the line moved by the radius, towards the side where the arc is, and by minus the centre;
  - a line of the tool tangent to an arc of the piece: the same as a corner on the edge, where the corner is the point of the arc the line touches;
  - an arc of the tool tangent to an arc of the piece: an arc around the centre of the piece arc minus the centre of the tool arc, of radius
    R + r (outside each other) or |R - r| (one inside the other).
A curve is only kept where the point of touch really lies on both pieces (the angle of the point of touch is inside the range of the arc).
Whether the tool is free on a curve, and where two curves meet, is decided by `tip_walk.py`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from ..constants import GEOMETRY_TOLERANCE_MM
from ..geometry import ArcSegment, LineSegment, Point, Segment
from ..geometry.arc_sweep import arc_at, ccw_range
from ..geometry.tool_edges import ToolLoop, translated_segment

Range = tuple[float, float]  # the angles a1 > a0 an arc covers, counter-clockwise


def _within(angle: float, span: Range) -> bool:
    along = (angle - span[0]) % math.tau
    return along <= span[1] - span[0] + GEOMETRY_TOLERANCE_MM or along >= math.tau - GEOMETRY_TOLERANCE_MM


def _shifted(span: Range, by: float) -> Range:
    return span[0] + by, span[1] + by


def _common(a: Range, b: Range) -> list[Range]:
    """The angles that are in both ranges (a whole turn is tried either way)."""
    found: list[Range] = []
    for turn in (-1, 0, 1):
        low, high = max(a[0], b[0] + turn * math.tau), min(a[1], b[1] + turn * math.tau)
        if high - low > GEOMETRY_TOLERANCE_MM:
            found.append((low, high))
    return found


def _unique(points: Iterable[Point]) -> list[Point]:
    seen: dict[tuple[int, int], Point] = {}
    for point in points:
        seen.setdefault((round(point.x / GEOMETRY_TOLERANCE_MM), round(point.z / GEOMETRY_TOLERANCE_MM)), point)
    return list(seen.values())


def _degenerate(segment: Segment) -> bool:
    return isinstance(segment, LineSegment) and segment.length <= GEOMETRY_TOLERANCE_MM


def _frame(line: LineSegment) -> tuple[float, float]:
    """The unit normal of a line."""
    dx, dz = line.end.x - line.start.x, line.end.z - line.start.z
    length = math.hypot(dx, dz)
    return -dz / length, dx / length


def _corner_on_edge(edge: Segment, corner: Point) -> list[Segment]:
    """The tip positions where the edge passes through the corner of the part."""
    if isinstance(edge, LineSegment):
        return [LineSegment(Point(corner.x - edge.start.x, corner.z - edge.start.z), Point(corner.x - edge.end.x, corner.z - edge.end.z))]
    start, end = ccw_range(edge)
    arc = arc_at(Point(corner.x - edge.center.x, corner.z - edge.center.z), edge.radius, start + math.pi, end + math.pi)
    return [arc] if arc is not None else []


def _arc_on_line(edge: ArcSegment, line: LineSegment) -> list[Segment]:
    nx, nz = _frame(line)
    span = ccw_range(edge)
    found: list[Segment] = []
    for side in (1, -1):
        if _within(math.atan2(-side * nz, -side * nx), span):  # the arc touches the line with the point at this angle
            found.append(translated_segment(line, side * edge.radius * nx - edge.center.x, side * edge.radius * nz - edge.center.z))
    return found


def _line_on_arc(edge: LineSegment, arc: ArcSegment) -> list[Segment]:
    nx, nz = _frame(edge)
    span = ccw_range(arc)
    found: list[Segment] = []
    for side in (1, -1):
        if _within(math.atan2(side * nz, side * nx), span):
            touch = Point(arc.center.x + side * arc.radius * nx, arc.center.z + side * arc.radius * nz)
            found += _corner_on_edge(edge, touch)
    return found


def _arc_on_arc(edge: ArcSegment, arc: ArcSegment) -> list[Segment]:
    on_part, on_tool = ccw_range(arc), ccw_range(edge)
    centre = Point(arc.center.x - edge.center.x, arc.center.z - edge.center.z)
    found: list[Segment] = []
    # (distance of the centres, turn from the direction of the centres to the point of touch on the part, and on the tool)
    for gap, part_turn, tool_turn in (
        (arc.radius + edge.radius, 0.0, math.pi),
        (arc.radius - edge.radius, 0.0, 0.0),
        (edge.radius - arc.radius, math.pi, math.pi),
    ):
        if gap <= GEOMETRY_TOLERANCE_MM:
            continue
        for low, high in _common(_shifted(on_part, -part_turn), _shifted(on_tool, -tool_turn)):
            piece = arc_at(centre, gap, low, high)
            if piece is not None:
                found.append(piece)
    return found


def _tangent(edge: Segment, piece: Segment) -> list[Segment]:
    if isinstance(edge, ArcSegment) and isinstance(piece, LineSegment):
        return _arc_on_line(edge, piece)
    if isinstance(edge, LineSegment) and isinstance(piece, ArcSegment):
        return _line_on_arc(edge, piece)
    if isinstance(edge, ArcSegment) and isinstance(piece, ArcSegment):
        return _arc_on_arc(edge, piece)
    return []


def tool_features(tool: list[ToolLoop]) -> tuple[list[Segment], list[Point]]:
    """The edges of the tool that have a length, and its corners (each once)."""
    edges = [edge.segment for loop in tool for edge in loop if not _degenerate(edge.segment)]
    return edges, _unique(point for edge in edges for point in (edge.start, edge.end))


def _kept(curves: list[Segment]) -> list[Segment]:
    return [curve for curve in curves if isinstance(curve, ArcSegment) or curve.length > GEOMETRY_TOLERANCE_MM]


def piece_curves(edges: list[Segment], corners: list[Point], piece: Segment) -> list[Segment]:
    """The curves along which the tool touches this one piece of the part: with a corner, with an edge, and with the two ends of the piece
    on its edges (an end shared with the next piece gives the same curves there too)."""
    if _degenerate(piece):
        return []
    found = [translated_segment(piece, -corner.x, -corner.z) for corner in corners]
    for edge in edges:
        found += _tangent(edge, piece)
        for corner in (piece.start, piece.end):
            found += _corner_on_edge(edge, corner)
    return _kept(found)


def contact_curves(tool: list[ToolLoop], pieces: list[Segment]) -> list[Segment]:
    """Every curve of the tip along which a corner or an edge of the tool touches a piece of the part (the tool with its tip at the origin)."""
    edges, corners = tool_features(tool)
    pieces = [piece for piece in pieces if not _degenerate(piece)]
    found: list[Segment] = []
    for piece in pieces:
        found += [translated_segment(piece, -corner.x, -corner.z) for corner in corners]
        for edge in edges:
            found += _tangent(edge, piece)
    for corner in _unique(point for piece in pieces for point in (piece.start, piece.end)):
        for edge in edges:
            found += _corner_on_edge(edge, corner)
    return _kept(found)
