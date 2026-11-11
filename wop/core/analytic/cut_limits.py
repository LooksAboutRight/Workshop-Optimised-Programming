"""Where a cut must stop and what it takes besides, for `roughing_cuts.py`: the top of the material over the end of a line, a way in that
comes down through material (a plunge), the far side of the axis on a part that turns, and an edge that does not cut meeting the material
that stands (the holder or the top of an insert taller than the depth of cut)."""

from __future__ import annotations

from ..constants import CUT_END_SNAP_MM, DIP_MIN_AREA_MM2, RIDE_END_FRACTION, RIDE_TRIM_STEPS
from ..geometry import LineSegment, Point, Segment
from ..geometry.intersect import fraction_along
from . import mirror
from ..geometry.chains import ChainError, Loop, crossings, difference, loop_area, split_at
from ..geometry.removal import cut
from ..geometry.tool_edges import ToolLoop


def column_top(
    material: list[Loop], level: float, low: float, axis: mirror.Flip | None, tolerance: float, keep: list[Loop] | None = None,
    connected_only: bool = False,
) -> float:
    """The top of the material to rough in the column at the end of a line (at `low`, from the line at `level` up): the highest point where it
    ends (on this side of the axis only when the material holds both sides of it, `axis`, else the ride would go round the part to reach the
    far side). `keep` (the part and its allowance) does not count. `connected_only` (lines across X): only the stretch that begins at the line
    counts. Across X the column above the end of a line runs along Z, beside the part: it may go through a part that is wider towards the
    front, and material further up, with air between, hides behind it where the ride along the contour cannot take it; riding up to it made
    the tool follow the contour far beyond the line before, the same stretch again for every line (the user, 2026-10-25). Along Z the column
    goes away from the part, and the ride up the contour does take what stands higher up. `level` when there is none."""
    at = low + 2 * tolerance
    spans = _spans(crossings(material, at, 1))
    if keep:
        spans = _without(spans, _spans(crossings(keep, at, 1)))
    near = Point(level, low)
    tops = [
        high for start, high in spans
        if (not connected_only or start <= level + CUT_END_SNAP_MM) and high > level + tolerance
        and (axis is None or near.distance_to(Point(high, low)) <= near.distance_to(axis.point(Point(high, low))) + tolerance)
    ]
    return max(tops, default=level)


def _spans(values: list[float]) -> list[tuple[float, float]]:
    """The stretches inside the loops along a line, from its sorted crossings (in, out, in, out ...)."""
    return list(zip(values[0::2], values[1::2]))


def _without(spans: list[tuple[float, float]], holes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The stretches with the holes taken out."""
    for hole_low, hole_high in holes:
        spans = [piece for low, high in spans for piece in ((low, min(high, hole_low)), (max(low, hole_high), high)) if piece[1] > piece[0]]
    return spans


def goes_into(way_in: list[Segment], tool: list[ToolLoop], material: list[Loop], tolerance: float) -> bool:
    """True when the last piece of the way in comes down onto the level (across the line) through material: a plunge (at the plunge feed),
    not the last clearance through air."""
    last = way_in[-1] if way_in else None
    if not isinstance(last, LineSegment) or abs(last.end.z - last.start.z) > tolerance or last.end.x >= last.start.x - tolerance:
        return False
    try:
        return sum(abs(loop_area(loop)) for loop in cut(material, tool, [last], tolerance)[1]) >= DIP_MIN_AREA_MM2
    except ChainError:
        return True  # on the safe side: the slower feed


def taken_on_both_sides(material: list[Loop], taken: list[Loop], axis: mirror.Flip | None, tolerance: float) -> list[Loop]:
    """The material after a cut on a part that turns: what the tool took on one side of the axis is gone on the other side too (`axis`: the
    reflection over the axis in the coordinates of the planner; None: the planner sees one side only, an outside block)."""
    if axis is None or not taken or not material:
        return material
    try:
        return difference(material, axis.loops(taken), tolerance)
    except ChainError:
        return material  # on the safe side: the far side as it was


def holder_stop(
    start: Point, end: Point, ride: list[Segment], tool: list[ToolLoop], material: list[Loop], tolerance: float, axis: mirror.Flip | None = None,
    while_cutting: bool = False,
) -> tuple[Point, list[Segment]]:
    """The line (from `start` to `end`) and its ride up, stopped where an edge of the tool that does not cut first meets the material that
    stands (`replay.holder_meets`): a tool taller than the depth of cut reaches into the layers above, and where a line above was cut
    short (its tool could not reach further), material stays there. What the tool cannot take that way stays (the note of the block).
    `while_cutting` (lines across X): the ride also ends where it no longer cuts (`_cutting_until`): beside a part that is wider towards the
    front it would follow the contour up past what stands under it, the same stretch again for every line (the user, 2026-10-25)."""
    from .replay import holder_meets  # late: the replay imports this module

    pieces = [LineSegment(start, end), *ride]
    standing = material
    for index, piece in enumerate(pieces):
        if piece.start.distance_to(piece.end) <= tolerance:
            continue  # a line of no length (a pass along the contour has none)
        place = holder_meets(piece, tool, standing, tolerance, axis)
        if place is not None:
            if index == 0:
                return place, []
            head = split_at(piece, [fraction_along(piece, place)])[0] if place.distance_to(piece.start) > tolerance else None
            return end, [*ride[:index - 1], *([head] if head is not None else [])]
        if while_cutting and index > 0:
            until = _cutting_until(piece, tool, standing, tolerance)
            if until <= 0:
                return end, ride[:index - 1]  # this piece and the ones after it cut nothing
            if until < 1:
                return end, [*ride[:index - 1], split_at(piece, [until])[0]]
        if index == len(pieces) - 1:
            break  # the material left after the last piece is not asked for
        try:
            standing, taken = cut(standing, tool, [piece], tolerance)
            standing = taken_on_both_sides(standing, taken, axis, tolerance)
        except ChainError:
            pass  # on the safe side: the material as it was
    return end, ride


def _cutting_until(piece: Segment, tool: list[ToolLoop], material: list[Loop], tolerance: float) -> float:
    """How far along the piece (0 to 1) the tool still takes material (`DIP_MIN_AREA_MM2` or more from there to the end of the piece): 0
    when the piece takes nothing, 1 when its last part still takes something. On the safe side (1) where the boolean cannot decide."""
    def takes(fraction: float) -> bool:
        rest = split_at(piece, [fraction])[-1] if fraction > 0 else piece
        try:
            return sum(abs(loop_area(loop)) for loop in cut(material, tool, [rest], tolerance)[1]) >= DIP_MIN_AREA_MM2
        except ChainError:
            return True

    if not takes(0.0):
        return 0.0
    if takes(RIDE_END_FRACTION):
        return 1.0
    low, high = 0.0, RIDE_END_FRACTION  # takes from `low` on, not from `high` on
    for _ in range(RIDE_TRIM_STEPS):
        middle = (low + high) / 2
        if takes(middle):
            low = middle
        else:
            high = middle
    return high

