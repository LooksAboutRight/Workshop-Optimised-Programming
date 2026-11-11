"""Pieces that a cut has separated from the part (a part-off groove, a facing cut through a ring ...).

Only the piece that is held stays. That is the piece that reaches the lowest Z (the chuck end). When two pieces reach
the same lowest Z (a ring around another one), the grip decides: gripped from the inside the piece nearer the axis is
held, in every other case (also no workholding at all) the piece farther from the axis.
"""

from __future__ import annotations

from ..constants import CUT_OFF_MIN_AREA_MM2, GEOMETRY_TOLERANCE_MM
from ..geometry.region import Region


def split_off(residual: Region, grip_inside: bool = False) -> tuple[Region, Region]:
    """(the held part, what was cut off). One piece or none: nothing is cut off."""
    pieces = residual.pieces()
    real = [piece for piece in pieces if piece.area >= CUT_OFF_MIN_AREA_MM2]
    if len(pieces) <= 1 or not real:
        return residual, Region.empty()
    lowest = min(piece.bounds.min_z for piece in real)
    candidates = [piece for piece in real if piece.bounds.min_z <= lowest + GEOMETRY_TOLERANCE_MM]
    if grip_inside:
        held = min(candidates, key=lambda piece: piece.bounds.min_x)
    else:
        held = max(candidates, key=lambda piece: piece.bounds.max_x)
    dropped = Region.empty()
    for piece in pieces:
        if piece is not held:
            dropped = dropped.union(piece)
    if dropped.area < CUT_OFF_MIN_AREA_MM2:
        return held, Region.empty()
    return held, dropped
