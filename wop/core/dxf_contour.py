"""Turn the lines and arcs of a drawing into a contour definition (requirement C6).

This module knows nothing about DXF files: the adapter reads a file into a
`DxfDrawing` (lines and arcs in the drawing plane, in mm). Here the pieces are
placed on the lathe (which drawing axis is Z), joined into one chain, turned the
right way round (starting at the highest Z) and written as steps the contour
editor can edit. Whatever is left out is named in the messages.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .constants import (
    DXF_AXIS_TOLERANCE_MM,
    DXF_EXACT_START_TOLERANCE_MM,
    DEGREES_PER_TURN,
    DXF_JOIN_TOLERANCE_MM,
    DXF_LABEL_DISTANCE_MM,
    DXF_MIN_LINE_LENGTH_MM,
    GEOMETRY_TOLERANCE_MM,
)
from .contour import ArcCenterStep, ArcRadiusStep, ContourDefinition, ContourError, LineStep, NamedPoint, Step
from .geometry import ArcDirection, Point

DrawingPoint = tuple[float, float]


class DxfAxes(Enum):
    """Which way the part lies in the drawing."""

    HORIZONTAL = "spindle axis horizontal (drawing X = Z, drawing Y = radius)"
    VERTICAL = "spindle axis vertical (drawing Y = Z, drawing X = radius)"


@dataclass(frozen=True)
class DxfLine:
    start: DrawingPoint
    end: DrawingPoint


@dataclass(frozen=True)
class DxfArc:
    """Counter-clockwise from start_deg to end_deg (as in DXF)."""

    center: DrawingPoint
    radius: float
    start_deg: float
    end_deg: float


@dataclass(frozen=True)
class DxfPoint:
    """A marker of the drawing with a name (a POINT and the TEXT next to it), in the drawing plane, mm."""

    name: str
    position: DrawingPoint


@dataclass(frozen=True)
class DxfDrawing:
    entities: tuple[DxfLine | DxfArc, ...]
    notes: tuple[str, ...] = ()  # what the reader ignored or converted
    points: tuple[DxfPoint, ...] = ()  # named points (used by `shape_from_drawing` only)


@dataclass(frozen=True)
class DxfImport:
    definition: ContourDefinition
    messages: tuple[str, ...] = field(default_factory=tuple)
    points: tuple[NamedPoint, ...] = ()  # named points, placed like the outline (shape import only)


@dataclass
class _Piece:
    start: Point
    end: Point
    center: Point | None = None  # None: a straight line
    direction: ArcDirection | None = None
    radius: float = 0
    sweep: float = 0

    @property
    def is_arc(self) -> bool:
        return self.center is not None

    def reversed(self) -> "_Piece":
        if self.center is None or self.direction is None:
            return _Piece(self.end, self.start)
        flipped = ArcDirection.CW if self.direction is ArcDirection.CCW else ArcDirection.CCW
        return _Piece(self.end, self.start, self.center, flipped, self.radius, self.sweep)

    @property
    def length(self) -> float:
        return self.radius * self.sweep if self.is_arc else self.start.distance_to(self.end)


def _arc_points(arc: DxfArc) -> tuple[DrawingPoint, DrawingPoint, DrawingPoint, float]:
    """Start, middle and end of the arc in the drawing, and its sweep in radians."""
    sweep = math.radians((arc.end_deg - arc.start_deg) % DEGREES_PER_TURN)
    if sweep <= GEOMETRY_TOLERANCE_MM:
        raise ContourError("an arc of the drawing is a full circle or has no length")
    start = math.radians(arc.start_deg)
    cx, cy = arc.center

    def at(angle: float) -> DrawingPoint:
        return (cx + arc.radius * math.cos(angle), cy + arc.radius * math.sin(angle))

    return at(start), at(start + sweep / 2), at(start + sweep), sweep


def _lathe_pieces(
    drawing: DxfDrawing, axes: DxfAxes, messages: list[str], as_drawn: bool = False
) -> list[_Piece]:
    samples: list[DrawingPoint] = []
    raw: list[tuple[DxfLine | DxfArc, tuple]] = []
    for entity in drawing.entities:
        if isinstance(entity, DxfLine):
            raw.append((entity, (entity.start, entity.end)))
        else:
            start, middle, end, sweep = _arc_points(entity)
            raw.append((entity, (start, middle, end, sweep)))
        samples += [p for p in raw[-1][1] if isinstance(p, tuple)]
    radius_index = 1 if axes is DxfAxes.HORIZONTAL else 0
    radii = [p[radius_index] for p in samples]
    mirror = (
        not as_drawn  # a shape keeps its place: nothing is mirrored or moved
        and bool(radii) and max(radii) <= DXF_AXIS_TOLERANCE_MM and min(radii) < -DXF_AXIS_TOLERANCE_MM
    )
    if mirror:
        messages.append("the drawing lies below the spindle axis: mirrored to positive radii")

    def place(p: DrawingPoint) -> Point:
        z, x = (p[0], p[1]) if axes is DxfAxes.HORIZONTAL else (p[1], p[0])
        return Point(-x if mirror else x, z)

    pieces: list[_Piece] = []
    for entity, data in raw:
        if isinstance(entity, DxfLine):
            start, end = place(data[0]), place(data[1])
            if start.distance_to(end) <= DXF_MIN_LINE_LENGTH_MM:
                messages.append("a line without length was ignored")
                continue
            pieces.append(_Piece(start, end))
            continue
        a, m, b, sweep = data
        start, middle, end, center = place(a), place(m), place(b), place(entity.center)
        cross = (start.x - center.x) * (middle.z - center.z) - (start.z - center.z) * (middle.x - center.x)
        direction = ArcDirection.CCW if cross > 0 else ArcDirection.CW
        pieces.append(_Piece(start, end, center, direction, entity.radius, sweep))
    return pieces


def _components(pieces: list[_Piece]) -> tuple[list[list[int]], list[tuple[int, int]]]:
    """Group the end points into nodes; return the pieces of each connected chain."""
    nodes: list[Point] = []

    def node_of(point: Point) -> int:
        for index, known in enumerate(nodes):
            if known.distance_to(point) <= DXF_JOIN_TOLERANCE_MM:
                return index
        nodes.append(point)
        return len(nodes) - 1

    edges = [(node_of(p.start), node_of(p.end)) for p in pieces]
    parent = list(range(len(nodes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for index, (a, _b) in enumerate(edges):
        groups.setdefault(find(a), []).append(index)
    return list(groups.values()), edges


def _walk(pieces: list[_Piece], edges: list[tuple[int, int]], members: list[int]) -> list[_Piece]:
    """Order the pieces of one chain from one end to the other (raises for loops and branches)."""
    degree: dict[int, int] = {}
    for index in members:
        for node in edges[index]:
            degree[node] = degree.get(node, 0) + 1
    if any(a == b for a, b in (edges[i] for i in members)):
        raise ContourError("a piece of the drawing starts and ends at the same point")
    if any(count > 2 for count in degree.values()):
        raise ContourError("the drawing branches: more than two lines or arcs meet at one point")
    ends = [node for node, count in degree.items() if count == 1]
    if len(ends) != 2:
        raise ContourError(
            "the outline is closed; delete the lines that close it (for example the axis line and "
            "the chuck side) so that one open chain is left"
        )
    node, remaining, chain = ends[0], set(members), []
    while remaining:
        index = next(i for i in remaining if node in edges[i])
        remaining.discard(index)
        piece = pieces[index]
        if edges[index][0] != node:
            piece = piece.reversed()
        chain.append(piece)
        node = edges[index][1] if edges[index][0] == node else edges[index][0]
    return chain


def contour_from_drawing(drawing: DxfDrawing, axes: DxfAxes = DxfAxes.HORIZONTAL) -> DxfImport:
    """Join the drawing's lines and arcs to one contour definition. Raises ContourError."""
    messages: list[str] = list(drawing.notes)
    pieces = _lathe_pieces(drawing, axes, messages)
    on_axis = [
        p for p in pieces
        if not p.is_arc and abs(p.start.x) <= DXF_AXIS_TOLERANCE_MM and abs(p.end.x) <= DXF_AXIS_TOLERANCE_MM
    ]
    if on_axis:
        pieces = [p for p in pieces if p not in on_axis]
        messages.append(f"{len(on_axis)} line(s) on the spindle axis were left out")
    if not pieces:
        raise ContourError("the drawing has no lines or arcs to use")
    groups, edges = _components(pieces)
    groups.sort(key=lambda members: -sum(pieces[i].length for i in members))
    if len(groups) > 1:
        messages.append(
            f"{len(groups)} separate chains found: the longest is used, "
            f"{sum(len(g) for g in groups[1:])} piece(s) in {len(groups) - 1} other chain(s) were left out"
        )
    chain = _walk(pieces, edges, groups[0])
    if chain[0].start.z < chain[-1].end.z:
        chain = [piece.reversed() for piece in reversed(chain)]
        messages.append("the chain was turned round: a contour starts at its highest Z")

    start, steps = _steps_of_chain(chain, messages)
    return DxfImport(ContourDefinition(start, steps), tuple(messages))


def _steps_of_chain(chain: list[_Piece], messages: list[str]) -> tuple[Point, tuple[Step, ...]]:
    """The start point and the steps of an ordered chain of pieces (small gaps are closed and named in the messages)."""
    junctions: list[Point] = []
    gaps: list[float] = []
    for before, after in zip(chain, chain[1:]):
        gaps.append(before.end.distance_to(after.start))
        if before.is_arc:
            junctions.append(before.end)
        elif after.is_arc:
            junctions.append(after.start)
        else:
            junctions.append(Point((before.end.x + after.start.x) / 2, (before.end.z + after.start.z) / 2))
    junctions.append(chain[-1].end)
    closed_gaps = [g for g in gaps if g > GEOMETRY_TOLERANCE_MM]
    if closed_gaps:
        messages.append(f"{len(closed_gaps)} gap(s) up to {max(closed_gaps):.3f} mm closed")

    steps: list[Step] = []
    used_start = chain[0].start
    for piece, end in zip(chain, junctions):
        if not piece.is_arc or piece.center is None or piece.direction is None:
            steps.append(LineStep(end))
        elif used_start.distance_to(piece.start) <= DXF_EXACT_START_TOLERANCE_MM:
            steps.append(ArcCenterStep(end, piece.center, piece.direction))
        else:
            steps.append(ArcRadiusStep(end, piece.radius, piece.direction, piece.sweep > math.pi))
        used_start = end
    return chain[0].start, tuple(steps)


def _walk_loop(pieces: list[_Piece], edges: list[tuple[int, int]], members: list[int]) -> list[_Piece]:
    """Order the pieces of one closed loop (every end point shared by exactly two pieces), starting at its first piece."""
    degree: dict[int, int] = {}
    for index in members:
        for node in edges[index]:
            degree[node] = degree.get(node, 0) + 1
    if any(edges[i][0] == edges[i][1] for i in members):
        raise ContourError("a piece of the drawing starts and ends at the same point")
    if any(count > 2 for count in degree.values()):
        raise ContourError("the drawing branches: more than two lines or arcs meet at one point")
    if any(count < 2 for count in degree.values()):
        raise ContourError("the outline is not closed: a line or arc ends where nothing else starts")
    first = members[0]
    chain = [pieces[first]]
    node, remaining = edges[first][1], set(members) - {first}
    while remaining:
        index = next(i for i in remaining if node in edges[i])
        remaining.discard(index)
        piece = pieces[index]
        if edges[index][0] != node:
            piece = piece.reversed()
        chain.append(piece)
        node = edges[index][1] if edges[index][0] == node else edges[index][0]
    return chain


def name_markers(
    markers: list[DrawingPoint], labels: list[tuple[str, DrawingPoint]], limit_mm: float = DXF_LABEL_DISTANCE_MM
) -> tuple[DxfPoint, ...]:
    """Give every marker the text nearest to it (within `limit_mm`, each text once); the others are "point 1", ...

    The adapter reads the POINT entities as markers and the TEXT or MTEXT entities as labels.
    """
    free = list(range(len(labels)))
    named: list[DxfPoint] = []
    unnamed = 0
    for marker in markers:
        best = None
        for index in free:
            distance = math.dist(marker, labels[index][1])
            if distance <= limit_mm and (best is None or distance < best[0]):
                best = (distance, index)
        text = labels[best[1]][0].strip() if best else ""
        if best:
            free.remove(best[1])
        if not text:
            unnamed += 1
            text = f"point {unnamed}"
        named.append(DxfPoint(text, marker))
    return tuple(named)


def shape_from_drawing(drawing: DxfDrawing) -> DxfImport:
    """A closed shape exactly as drawn (workholding items, holders, turrets, tools), with its named points.

    The drawing is read like a lathe drawing: spindle axis horizontal, drawing X = Z, drawing Y = radius. Nothing is
    moved, turned or mirrored, no line is dropped (also not one on the axis): the origin of the drawing stays the
    origin of the shape. The outline must be one closed loop; raises ContourError otherwise.
    """
    messages: list[str] = list(drawing.notes)
    pieces = _lathe_pieces(drawing, DxfAxes.HORIZONTAL, messages, as_drawn=True)
    if not pieces:
        raise ContourError("the drawing has no lines or arcs to use")
    groups, edges = _components(pieces)
    groups.sort(key=lambda members: -sum(pieces[i].length for i in members))
    if len(groups) > 1:
        messages.append(
            f"{len(groups)} separate outlines found: the longest is used, "
            f"{sum(len(g) for g in groups[1:])} piece(s) in {len(groups) - 1} other outline(s) were left out"
        )
    chain = _walk_loop(pieces, edges, groups[0])
    start, steps = _steps_of_chain(chain, messages)
    points = tuple(NamedPoint(point.name, point.position[1], point.position[0]) for point in drawing.points)
    return DxfImport(ContourDefinition(start, steps), tuple(messages), points)
