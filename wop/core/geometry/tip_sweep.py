"""What the tool sweeps on a straight move, as one region: the tip of the tool (its cutting edges, closed by a chord) swept along the move.

The rule (the user's decision, 2026-10-22): a move removes the material the tool sweeps. The cutting edges of a tool are one run along its
outline (a flank, the nose arc, the other flank; the front and the bottom of a block). That run, closed by the straight chord from its end back
to its start, is the tip of the tool. When the tip is convex and the chord lies inside the tool, the region the tip sweeps along a straight
move is known at once: the half of its border that faces backwards at the start, the half that faces forwards moved to the end, and the two
lines along the move that join them (the arcs cut where their tangent is parallel to the move). One region per move instead of one strip per
cutting edge, so one split of the material. It removes the same material as the strips as long as no material is inside the tool where no
cutting edge passed, and that is a collision the replay reports (`replay.py`: a holder in the material). A tool whose tip is not convex, or a
move along an arc, is swept with the strips of its cutting edges (`removal.strips_along`).
"""

from __future__ import annotations

from collections.abc import Sequence

import math

from ..constants import GEOMETRY_TOLERANCE_MM, MIDPOINT_FRACTION
from .primitives import ArcDirection, ArcSegment, LineSegment, Point, Segment
from .intersect import fraction_along, intersections, point_of
from .distance import distance_to_segment
from .chains import Loop, closed_loop, crossings, loop_area, reversed_segment, split_at
from .tool_edges import ToolLoop, translated_segment


def _tangent(segment: Segment, point: Point) -> tuple[float, float]:
    """The unit direction of travel of the segment at the point."""
    if isinstance(segment, LineSegment):
        dx, dz = segment.end.x - segment.start.x, segment.end.z - segment.start.z
    else:
        sign = segment.turn
        dx, dz = -(point.z - segment.center.z) * sign, (point.x - segment.center.x) * sign
    length = math.hypot(dx, dz)
    return dx / length, dz / length


def _run(loop: ToolLoop) -> list[Segment] | None:
    """The cutting edges of the loop as one run in the order of the loop, or None when they are not one run (or there are none)."""
    count = len(loop)
    cutting = [edge.cutting for edge in loop]
    if not any(cutting) or all(cutting):
        return None
    starts = [i for i in range(count) if cutting[i] and not cutting[i - 1]]
    if len(starts) != 1:
        return None
    first = starts[0]
    run = []
    for step in range(count):
        edge = loop[(first + step) % count]
        if not edge.cutting:
            break
        run.append(edge.segment)
    return [segment for segment in run if not (isinstance(segment, LineSegment) and segment.length <= GEOMETRY_TOLERANCE_MM)]


def _convex(hull: Loop) -> bool:
    """True when the counter-clockwise loop turns left (or goes straight) at every corner and every arc bulges outwards."""
    for here, after in zip(hull, [*hull[1:], *hull[:1]]):
        if isinstance(here, ArcSegment) and here.direction is not ArcDirection.CCW:
            return False
        ax, az = _tangent(here, here.end)
        bx, bz = _tangent(after, after.start)
        if ax * bz - az * bx < -GEOMETRY_TOLERANCE_MM:
            return False
    return True


def _chord_inside(chord: LineSegment, outline: Sequence[Segment]) -> bool:
    """True when the chord runs inside the tool outline: its middle is inside and it crosses no edge between its ends."""
    middle = point_of(chord, MIDPOINT_FRACTION)
    if not any(distance_to_segment(middle, edge) <= GEOMETRY_TOLERANCE_MM for edge in outline):
        if sum(1 for z in crossings([tuple(outline)], middle.x, 0) if z > middle.z) % 2 == 0:
            return False
    for edge in outline:
        for point in intersections(chord, edge):
            if not (point.is_close(chord.start, GEOMETRY_TOLERANCE_MM) or point.is_close(chord.end, GEOMETRY_TOLERANCE_MM)):
                return False
    return True


def tip_hull(tool: Sequence[ToolLoop]) -> Loop | None:
    """The tip of the tool (its tip at the origin) as a convex counter-clockwise loop, or None when it is not one: the cutting edges are not one
    run in one loop, the run with its chord is not convex, or the chord leaves the tool."""
    runs = [(loop, run) for loop in tool if (run := _run(loop))]
    if len(runs) != 1 or any(edge.cutting for loop in tool for edge in loop if loop is not runs[0][0]):
        return None
    loop, run = runs[0]
    chord = LineSegment(run[-1].end, run[0].start)
    if chord.length <= GEOMETRY_TOLERANCE_MM:
        return None  # the cutting edges go all round: no chord, the strips are the way
    hull = closed_loop([*run, chord])
    if loop_area(hull) < 0:
        hull = tuple(reversed_segment(segment) for segment in reversed(hull))
    if not _convex(hull) or not _chord_inside(chord, [edge.segment for edge in loop]):
        return None
    return hull


def _split_for(hull: Loop, unit: tuple[float, float]) -> list[Segment]:
    """The pieces of the hull, every arc cut where its tangent is parallel to the move."""
    nx, nz = -unit[1], unit[0]
    pieces: list[Segment] = []
    for segment in hull:
        if isinstance(segment, ArcSegment):
            marks = []
            for sign in (1, -1):
                point = Point(segment.center.x + sign * segment.radius * nx, segment.center.z + sign * segment.radius * nz)
                if distance_to_segment(point, segment) <= GEOMETRY_TOLERANCE_MM:
                    marks.append(fraction_along(segment, point))
            pieces += split_at(segment, marks)
        else:
            pieces.append(segment)
    return pieces


def _facing_forward(piece: Segment, unit: tuple[float, float]) -> bool:
    """True when the outward normal of the piece (of a counter-clockwise loop) points along the move."""
    middle = point_of(piece, MIDPOINT_FRACTION)
    tx, tz = _tangent(piece, middle)
    return tz * unit[0] - tx * unit[1] > GEOMETRY_TOLERANCE_MM  # the outward normal of a counter-clockwise loop is (tz, -tx)


def swept_tip(hull: Loop, start: Point, vector: tuple[float, float]) -> Loop | None:
    """The region the tip `hull` (its tip at the origin) sweeps when the tool tip goes from `start` by `vector`, counter-clockwise; None for a
    move of no length."""
    length = math.hypot(*vector)
    if length <= GEOMETRY_TOLERANCE_MM:
        return None
    unit = (vector[0] / length, vector[1] / length)
    pieces = [translated_segment(piece, start.x, start.z) for piece in _split_for(hull, unit)]
    forward = [_facing_forward(piece, unit) for piece in pieces]
    count = len(pieces)
    first = next((i for i in range(count) if not forward[i] and forward[i - 1]), None)  # the first piece of the back half
    if first is None:
        return None
    pieces, forward = pieces[first:] + pieces[:first], forward[first:] + forward[:first]
    back = [piece for piece, ahead in zip(pieces, forward) if not ahead]
    front = [piece for piece, ahead in zip(pieces, forward) if ahead]
    if forward != [False] * len(back) + [True] * len(front):
        return None  # not convex after all: the caller sweeps the edges one by one
    moved = [translated_segment(piece, *vector) for piece in front]
    ring = [*back, LineSegment(back[-1].end, moved[0].start), *moved, LineSegment(moved[-1].end, back[0].start)]
    return closed_loop(ring)
