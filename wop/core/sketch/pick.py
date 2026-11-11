"""Which point or piece of a sketch is near a position (for selecting with the mouse)."""

from __future__ import annotations

from ..geometry import Point
from ..geometry.distance import distance_to_segment
from .model import Piece, Sketch, SketchArc


def nearest_point(sketch: Sketch, position: Point, tolerance: float, skip: tuple[int, ...] = ()) -> int | None:
    """Id of the point closest to `position` within `tolerance`, or None."""
    best: tuple[float, int] | None = None
    for point_id, point in sketch.points.items():
        if point_id in skip:
            continue
        distance = position.distance_to(point.position)
        if distance <= tolerance and (best is None or distance < best[0]):
            best = (distance, point_id)
    return None if best is None else best[1]


def nearest_piece(sketch: Sketch, position: Point, tolerance: float, skip: set[int] | frozenset[int] = frozenset(), prefer: int | None = None) -> Piece | None:
    """The piece closest to `position` within `tolerance`, or None. `skip`: ids that cannot be picked; `prefer`: this piece wins when it is
    within the tolerance too (where several pieces lie on one place)."""
    best: tuple[float, Piece] | None = None
    for piece in sketch.selectable_pieces():
        if piece_id(piece) in skip:
            continue
        distance = distance_to_segment(position, sketch.segment(piece))
        if distance <= tolerance and (prefer == piece_id(piece) or best is None or distance < best[0]):
            if prefer == piece_id(piece):
                return piece
            best = (distance, piece)
    return None if best is None else best[1]


def piece_id(piece: Piece) -> int:
    return piece.arc_id if isinstance(piece, SketchArc) else piece.line_id


def piece_points(piece: Piece) -> set[int]:
    """Ids of every point a piece uses (an arc or circle includes its centre)."""
    points = {piece.start, piece.end}
    if isinstance(piece, SketchArc):
        points.add(piece.centre)
    return points
