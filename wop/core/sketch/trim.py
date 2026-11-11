"""Trim: cut a piece back to the nearest crossings on both sides of a clicked spot.

The piece between the two crossings (or between a crossing and the end of the piece) is removed. The new line end
sits on the piece it was cut by (a "point on" relation, or the very point of that piece if one lies there). If the
piece is cut in two places around the click, the rest on the far side becomes a new piece of the same kind. Relations
that refer to the trimmed piece itself (its length, radius, parallel to ...) are removed; those between points stay.
A circle needs two crossings; what is left is an arc.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Point
from .constants import POINT_TOLERANCE
from ..geometry.intersect import fraction_along, intersections
from .model import Piece, Sketch, SketchArc, SketchError, SketchLine


@dataclass(frozen=True)
class _Cut:
    fraction: float
    point: Point
    cutter: Piece


def _piece(sketch: Sketch, piece_id: int) -> Piece:
    if piece_id in sketch.lines:
        return sketch.lines[piece_id]
    if piece_id in sketch.arcs:
        return sketch.arcs[piece_id]
    raise SketchError("Click a line or an arc to trim")


def _cuts(sketch: Sketch, piece: Piece, piece_id: int, is_circle: bool) -> list[_Cut]:
    segment = sketch.segment(piece)
    found: list[_Cut] = []
    for other in sketch.pieces():
        other_id = other.arc_id if isinstance(other, SketchArc) else other.line_id
        if other_id == piece_id:
            continue
        for point in intersections(segment, sketch.segment(other)):
            at_end = point.distance_to(segment.start) <= POINT_TOLERANCE or point.distance_to(segment.end) <= POINT_TOLERANCE
            if (at_end and not is_circle) or any(point.distance_to(c.point) <= POINT_TOLERANCE for c in found):
                continue
            found.append(_Cut(fraction_along(segment, point), point, other))
    return sorted(found, key=lambda cut: cut.fraction)


def _point_at(sketch: Sketch, cut: _Cut) -> int:
    """The sketch point at a crossing: one that is there already, else a new point held on the cutting piece."""
    for point_id, point in sketch.points.items():
        if point.position.distance_to(cut.point) <= POINT_TOLERANCE:
            return point_id
    new_point = sketch.add_point(cut.point.x, cut.point.z)
    if isinstance(cut.cutter, SketchLine):
        sketch.add_constraint("point_on_line", (new_point, cut.cutter.line_id))
    else:
        sketch.add_constraint("point_on_circle", (new_point, cut.cutter.arc_id))
    return new_point


def trim_piece(sketch: Sketch, piece_id: int, position: Point) -> None:
    piece = _piece(sketch, piece_id)
    is_circle = isinstance(piece, SketchArc) and piece.start == piece.end
    cuts = _cuts(sketch, piece, piece_id, is_circle)
    click = fraction_along(sketch.segment(piece), position)
    if is_circle:
        _trim_circle(sketch, piece, piece_id, cuts, click)
        return
    click = max(0, min(1, click))
    below = [cut for cut in cuts if cut.fraction < click]
    above = [cut for cut in cuts if cut.fraction >= click]
    sketch.forget_piece_constraints(piece_id)
    if not below and not above:
        sketch.delete_piece(piece_id)
        return
    low = _point_at(sketch, below[-1]) if below else None
    high = _point_at(sketch, above[0]) if above else None
    if low is None:
        sketch.update_piece(piece_id, start=high)
    elif high is None:
        sketch.update_piece(piece_id, end=low)
    else:
        far_end = piece.end
        sketch.update_piece(piece_id, end=low)
        if isinstance(piece, SketchLine):
            sketch.add_line(high, far_end, piece.construction, piece.cutting, piece.centre_line, piece.reference)
        else:
            new_arc = sketch.add_arc(piece.centre, high, far_end, piece.direction, piece.construction, piece.cutting)
            sketch.add_constraint("equal_radius", (piece_id, new_arc))
    sketch.drop_unused_points()


def _trim_circle(sketch: Sketch, piece: SketchArc, piece_id: int, cuts: list[_Cut], click: float) -> None:
    if len(cuts) < 2:
        raise SketchError("A circle needs two crossings before it can be trimmed")
    before = [cut for cut in cuts if cut.fraction < click]
    after = [cut for cut in cuts if cut.fraction >= click]
    low = before[-1] if before else cuts[-1]  # wrapping round the start of the circle
    high = after[0] if after else cuts[0]
    sketch.forget_piece_constraints(piece_id)
    start, end = _point_at(sketch, high), _point_at(sketch, low)
    sketch.update_piece(piece_id, start=start, end=end)
    sketch.drop_unused_points()
