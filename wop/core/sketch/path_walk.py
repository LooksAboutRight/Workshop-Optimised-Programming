"""The path of a custom path block drawn in the sketch editor: which pieces run in which order.

A path starts at the safe point (a locked point of the sketch) and goes piece after piece. It may come back to a place it has been
(a feed in and a rapid out along the same line), so a point can have more than two pieces: at such a place the piece drawn first is
taken next. A piece is walked from the end that meets the previous piece, whichever way it was drawn. Pieces that the walk does not
reach are a problem (they can be made construction lines).
"""

from __future__ import annotations

from ..constants import SAFE_POINT_KEY
from ..geometry import Segment
from .constants import POINT_TOLERANCE
from .loops import reversed_segment
from .model import Piece, Sketch, SketchArc


def _representatives(sketch: Sketch) -> dict[int, int]:
    """Points at the same place count as one point."""
    representative: dict[int, int] = {}
    seen: list[tuple[object, int]] = []
    for point_id, point in sketch.points.items():
        for position, first in seen:
            if point.position.distance_to(position) <= POINT_TOLERANCE:
                representative[point_id] = first
                break
        else:
            seen.append((point.position, point_id))
            representative[point_id] = point_id
    return representative


def walk_path(sketch: Sketch) -> tuple[list[tuple[Piece, bool]], list[str]]:
    """The pieces in travel order (each with whether it is walked from its start to its end) and what is wrong with the path."""
    start = sketch.locked_points.get(SAFE_POINT_KEY)
    if start is None:
        return [], ["The safe point is missing"]
    rep = _representatives(sketch)
    pieces = [piece for piece in sketch.pieces() if not piece.construction]
    problems = []
    if any(isinstance(piece, SketchArc) and piece.start == piece.end for piece in pieces):
        problems.append("A circle cannot be part of a path: make an arc")
    walked: list[tuple[Piece, bool]] = []
    unused = list(pieces)
    here = rep[start]
    while True:
        next_piece = next((p for p in unused if here in (rep[p.start], rep[p.end])), None)  # the piece drawn first
        if next_piece is None:
            break
        forward = rep[next_piece.start] == here
        walked.append((next_piece, forward))
        unused.remove(next_piece)
        here = rep[next_piece.end if forward else next_piece.start]
    if not walked:
        problems.append("Draw the path: its first line starts at the safe point (the green square)")
    elif unused:
        problems.append(
            f"{len(unused)} line(s) or arc(s) do not follow the path from the safe point: draw them in the order the tool moves, "
            "or make them construction lines"
        )
    return walked, problems


def path_segments(sketch: Sketch) -> tuple[list[Segment], list[str]]:
    """The segments of the path in travel order (the hook of the mode) and the problems."""
    walked, problems = walk_path(sketch)
    return [sketch.segment(piece) if forward else reversed_segment(sketch.segment(piece)) for piece, forward in walked], problems
