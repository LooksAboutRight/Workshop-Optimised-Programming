"""Loops with the features at the scale of the snap distance taken out.

A cut leaves a border with steps and slivers a thousandth of a millimetre long (the nose arc of one cut next to the straight edge of the one
before): far below the user's roughing accuracy, but the next boolean cannot decide a corner that close to an edge. So after every cut a piece
shorter than the snap distance is taken out (the straight neighbour is moved to where the other one begins) and straight pieces that follow each
other on one line are one piece. A loose loop thinner than the roughing accuracy of the user (`CUT_END_SNAP_MM`; its area over half its length: a
needle of two pieces on each other, a sliver or a speck the cuts left) is no material to rough and is dropped.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..constants import CUT_JITTER_MM, CUT_TOLERANCE_FACTORS, GEOMETRY_TOLERANCE_MM, MIN_LOOP_PIECES
from .primitives import LineSegment, Segment
from .distance import distance_to_segment
from .chains import ChainError, Loop, closed_loop, intersection, loop_area
from .tool_edges import translated_segment


def _without_short(pieces: list[Segment], snap: float) -> list[Segment]:
    """The first piece shorter than `snap` with a straight neighbour is taken out, again until there is none."""
    changed = True
    while changed and len(pieces) > MIN_LOOP_PIECES:
        changed = False
        for index, piece in enumerate(pieces):
            if piece.length >= snap:
                continue
            before, after = (index - 1) % len(pieces), (index + 1) % len(pieces)
            if isinstance(pieces[before], LineSegment):
                pieces[before] = LineSegment(pieces[before].start, pieces[after].start)
            elif isinstance(pieces[after], LineSegment):
                pieces[after] = LineSegment(pieces[before].end, pieces[after].end)
            else:
                continue
            del pieces[index]
            changed = True
            break
    return pieces


def _merged(pieces: Sequence[Segment]) -> list[Segment]:
    """Straight pieces in a row on one line are one piece."""
    merged: list[Segment] = []
    for piece in pieces:
        if merged and isinstance(piece, LineSegment) and isinstance(merged[-1], LineSegment):
            whole = LineSegment(merged[-1].start, piece.end)
            if whole.length > GEOMETRY_TOLERANCE_MM and distance_to_segment(merged[-1].end, whole) <= GEOMETRY_TOLERANCE_MM:
                merged[-1] = whole
                continue
        merged.append(piece)
    return merged


def tidy(loop: Loop, snap: float) -> Loop:
    """The loop with the pieces shorter than `snap` taken out and collinear lines joined (the loop as it was when that leaves nothing sensible)."""
    pieces = _merged(_without_short(list(loop), snap))
    if len(pieces) > 1 and isinstance(pieces[0], LineSegment) and isinstance(pieces[-1], LineSegment):  # the loop starts in the middle of a line
        whole = LineSegment(pieces[-1].start, pieces[0].end)
        if distance_to_segment(pieces[0].start, whole) <= GEOMETRY_TOLERANCE_MM:
            pieces = [whole, *pieces[1:-1]]
    if len(pieces) < MIN_LOOP_PIECES - 1:
        return loop
    try:
        return closed_loop(pieces)
    except ValueError:
        return loop


def tidied(loops: Sequence[Loop], snap: float, thinnest: float | None = None) -> list[Loop]:
    """The loops tidied, without the ones thinner than `thinnest` (default `snap`; on average: the area over half the length of the border)."""
    limit = snap if thinnest is None else thinnest
    kept: list[Loop] = []
    for loop in loops:
        neat = tidy(loop, snap)
        if abs(loop_area(neat)) > limit * sum(piece.length for piece in neat) / 2:
            kept.append(neat)
    return kept


def steady_intersection(a: Sequence[Loop], b: Sequence[Loop], tolerance: float) -> list[Loop]:
    """`a` and `b` as `chains.intersection` makes it, tried again where the boolean cannot decide (a corner of one exactly on the border of
    the other): with `b` moved by the small shifts of `CUT_JITTER_MM` (far below the roughing accuracy), then with a smaller tolerance
    (`CUT_TOLERANCE_FACTORS`). Raises the ChainError of the first try when all of them fail."""
    first_error = None
    for factor in (1, *CUT_TOLERANCE_FACTORS):
        for dx, dz in ((0.0, 0.0), *CUT_JITTER_MM):
            moved = b if dx == dz == 0 else [tuple(translated_segment(segment, dx, dz) for segment in loop) for loop in b]
            try:
                return intersection(a, moved, tolerance * factor)
            except ChainError as error:
                first_error = first_error or error
    raise first_error
