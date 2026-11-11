"""Chains of sketch pieces: which pieces join end to end into an open profile or a closed loop."""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import ArcDirection, ArcSegment, LineSegment, Segment
from .model import Piece, Sketch, SketchArc, SketchError

DEGREE_ENDPOINT = 1
DEGREE_PASS = 2


@dataclass(frozen=True)
class Chain:
    """Pieces in travel order. `forward[i]` False means piece i is walked from its end to its start."""

    pieces: tuple[Piece, ...]
    forward: tuple[bool, ...]
    closed: bool


def _ends(piece: Piece) -> tuple[int, int]:
    return piece.start, piece.end


def _piece_id(piece: Piece) -> int:
    return piece.arc_id if isinstance(piece, SketchArc) else piece.line_id


def find_chains(sketch: Sketch) -> list[Chain]:
    """All chains of the real (not construction) pieces. A point where three or more pieces meet is an error."""
    pieces = [p for p in sketch.pieces() if not p.construction]
    at_point: dict[int, list[Piece]] = {}
    for piece in pieces:
        for point_id in _ends(piece):
            at_point.setdefault(point_id, []).append(piece)
    for point_id, here in at_point.items():
        if len(here) > DEGREE_PASS:
            raise SketchError(f"{len(here)} pieces meet at point {point_id}")
    seen: set[int] = set()
    chains: list[Chain] = []
    open_ends = [pid for pid, here in at_point.items() if len(here) == DEGREE_ENDPOINT]
    starts = open_ends + [piece.start for piece in pieces]  # open chains first, then what is left is closed
    for point_id in starts:
        first = next((p for p in at_point[point_id] if _piece_id(p) not in seen), None)
        if first is not None:
            chains.append(_walk(point_id, first, at_point, seen))
    return chains


def _walk(start_point: int, first: Piece, at_point: dict[int, list[Piece]], seen: set[int]) -> Chain:
    ordered: list[Piece] = []
    forward: list[bool] = []
    point_id, piece = start_point, first
    closed = False
    while piece is not None:
        seen.add(_piece_id(piece))
        goes_forward = piece.start == point_id
        ordered.append(piece)
        forward.append(goes_forward)
        point_id = piece.end if goes_forward else piece.start
        if point_id == start_point:
            closed = True
            break
        piece = next((p for p in at_point[point_id] if _piece_id(p) not in seen), None)
    return Chain(tuple(ordered), tuple(forward), closed)


def reversed_segment(segment: Segment) -> Segment:
    """The same piece walked the other way."""
    if isinstance(segment, LineSegment):
        return LineSegment(segment.end, segment.start)
    direction = ArcDirection.CW if segment.direction is ArcDirection.CCW else ArcDirection.CCW
    return ArcSegment(segment.end, segment.start, segment.center, direction)


def chain_segments(sketch: Sketch, chain: Chain) -> list[Segment]:
    """The segments of a chain in travel order, reversed pieces turned round."""
    return [
        sketch.segment(piece) if goes_forward else reversed_segment(sketch.segment(piece))
        for piece, goes_forward in zip(chain.pieces, chain.forward)
    ]
