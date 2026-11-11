"""The material a move removes: what the tool sweeps (the user's rule, 2026-10-22).

On a straight move the tip of the tool (its cutting edges closed by a chord) is swept as one region (`tip_sweep.py`): one split of the
material per move. Otherwise (a move along an arc, a tool whose tip is not convex) every cutting edge draws a strip. Whatever the tool
enters, it enters through a cutting edge (the rule of `penetration.py`), so the two remove the same material; the holder removes nothing: a
holder that enters material is a collision, reported by the replay.

The strip of a line is a parallelogram; the strip of an arc is exact too: the arc, the arc moved by the vector and the two lines
that join their ends, with the arc cut where its tangent is parallel to the move (a strip that folds over itself is no region).
A path that is an arc (the way up along a curved contour) is swept exactly as well (`arc_sweep.py`): there are no chords anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence

import math

from ..constants import CHAIN_SNAP_MM, CUT_END_SNAP_MM, CUT_JITTER_MM, CUT_TOLERANCE_FACTORS, GEOMETRY_TOLERANCE_MM
from .primitives import ArcSegment, LineSegment, Point, Segment
from .intersect import fraction_along
from .distance import distance_to_segment
from .arc_sweep import arc_along_arc, line_along_arc
from .chains import ChainError, Loop, closed_loop, oriented, polygon_loop, reversed_segment, split_at, split_regions
from .tidy import tidied
from .tip_sweep import swept_tip, tip_hull
from .tool_edges import ToolLoop, placed, translated, translated_segment


def _arc_pieces(arc: ArcSegment, vector: tuple[float, float]) -> list[Segment]:
    """The arc cut where its tangent is parallel to the vector (there the strip would fold)."""
    length = math.hypot(*vector)
    nx, nz = -vector[1] / length, vector[0] / length
    marks = []
    for sign in (1, -1):
        point = Point(arc.center.x + sign * arc.radius * nx, arc.center.z + sign * arc.radius * nz)
        if distance_to_segment(point, arc) <= GEOMETRY_TOLERANCE_MM:
            marks.append(fraction_along(arc, point))
    return split_at(arc, marks)


def _strip(segment: Segment, vector: tuple[float, float]) -> Loop | None:
    dx, dz = vector
    if isinstance(segment, LineSegment):
        a, b = segment.start, segment.end
        cross = (b.x - a.x) * dz - (b.z - a.z) * dx
        if abs(cross) <= GEOMETRY_TOLERANCE_MM:
            return None  # an edge that moves along itself sweeps nothing
        return oriented(polygon_loop([a, b, translated(b, dx, dz), translated(a, dx, dz)]), True)
    moved = translated_segment(segment, dx, dz)
    ring: list[Segment] = [segment, LineSegment(segment.end, moved.end), reversed_segment(moved), LineSegment(moved.start, segment.start)]
    return oriented(closed_loop(ring), True)


def strips(tool: Sequence[ToolLoop], start: Point, vector: tuple[float, float]) -> list[Loop]:
    """The strips the cutting edges of the tool draw when it moves from `start` by `vector`."""
    loops: list[Loop] = []
    for loop in placed(tool, start):
        for edge in loop:
            if not edge.cutting:
                continue
            for piece in (_arc_pieces(edge.segment, vector) if isinstance(edge.segment, ArcSegment) else [edge.segment]):
                strip = _strip(piece, vector)
                if strip is not None:
                    loops.append(strip)
    return loops


def strips_along(tool: Sequence[ToolLoop], piece: Segment) -> list[Loop]:
    """The strips the cutting edges of the tool draw while its tip goes along a line or an arc `piece` (the tool at the start of it)."""
    if isinstance(piece, LineSegment):
        return strips(tool, piece.start, (piece.end.x - piece.start.x, piece.end.z - piece.start.z))
    loops: list[Loop] = []
    for loop in placed(tool, piece.start):
        for edge in loop:
            if edge.cutting:
                loops += arc_along_arc(edge.segment, piece) if isinstance(edge.segment, ArcSegment) else line_along_arc(edge.segment.start, edge.segment.end, piece)
    return loops


def _shifted(loop: Loop, dx: float, dz: float) -> Loop:
    return tuple(translated_segment(segment, dx, dz) for segment in loop)


def _cut_once(
    material: Sequence[Loop], tool: Sequence[ToolLoop], path: Sequence[Segment], tolerance: float, shift: tuple[float, float],
) -> tuple[list[Loop], list[Loop]]:
    left = list(material)
    removed: list[Loop] = []
    hull = tip_hull(tool)
    for piece in path:
        swept = swept_tip(hull, piece.start, (piece.end.x - piece.start.x, piece.end.z - piece.start.z)) if hull is not None and isinstance(piece, LineSegment) else None
        for strip in [swept] if swept is not None else strips_along(tool, piece):
            strip = _shifted(strip, *shift) if shift != (0, 0) else strip
            taken, left = split_regions(left, [strip], tolerance)
            removed += taken
            if not left:
                return left, removed
    return left, removed


def cut(material: Sequence[Loop], tool: Sequence[ToolLoop], path: Sequence[Segment], tolerance: float) -> tuple[list[Loop], list[Loop]]:
    """The material after the cutting edges of the tool have followed the path (lines and arcs, each starting where the one before ends),
    and the pieces of material that were removed (each piece is taken from the material as it was, so they do not overlap).

    A corner of a strip that lies a few thousandths of a millimetre from an edge of the material is a coincidence the boolean cannot
    always decide; then the whole cut is repeated with every strip moved by the same small shift (`CUT_JITTER_MM`, far below the
    roughing accuracy), then with a smaller tolerance (`CUT_TOLERANCE_FACTORS`: a sliver thinner than the snap distance), and the error is raised only when all of them fail. The border of the material is tidied (`tidy.py`) before and after, and loose loops thinner than the roughing accuracy are dropped."""
    material = tidied(material, CHAIN_SNAP_MM, CUT_END_SNAP_MM)
    for factor in (1, *CUT_TOLERANCE_FACTORS):
        for shift in ((0, 0), *CUT_JITTER_MM):
            try:
                left, removed = _cut_once(material, tool, path, tolerance * factor, shift)
                return tidied(left, CHAIN_SNAP_MM, CUT_END_SNAP_MM), removed
            except ChainError:
                continue
    raise ChainError("the cut could not be worked out")
