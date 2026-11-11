"""The material under the lowest lines: which stretches of a line have no other line under them, and the pass that follows the contour there.

A line is cut at the level of its radius. Where the contour lies below it, another line one depth of cut deeper is cut as well, and the wedge between
them is taken by the ride-up. Where no line lies under a stretch, the contour is below the line by less than a depth of cut and the material between
them is still there and reachable: the bottom of a pocket, a dip in the contour. So a stretch of a line with no other line of a smaller radius under it
(`uncovered`, found by one sweep from the deepest level up, with the ranges already seen merged) gets a pass: the tool starts at the shortened
start of the stretch, where it has stood already, follows the contour down as far as the tool may stand and up again to the height of the line above
(`follow_dip`: the walks of `tip_walk.py`, down and up in turn). A pass that cuts nothing is dropped by the caller.
"""

from __future__ import annotations

from ..constants import GEOMETRY_TOLERANCE_MM, TIP_WALK_MAX_PIECES, WANTED_SPAN_MIN_MM
from ..geometry import Point, Segment
from ..geometry.penetration import RegionIndex
from .tip_walk import TipCurves, tip_walk
from ..geometry.tool_edges import ToolLoop

Range = tuple[float, float]


def _merged(ranges: list[Range]) -> list[Range]:
    merged: list[Range] = []
    for low, high in sorted(ranges):
        if merged and low <= merged[-1][1] + GEOMETRY_TOLERANCE_MM:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


def _minus(low: float, high: float, covered: list[Range]) -> list[Range]:
    """The parts of the range `low`..`high` that no range of `covered` (merged, sorted) overlaps, the ones shorter than the sliver limit left out."""
    parts: list[Range] = []
    start = low
    for c_low, c_high in covered:
        if c_high <= start:
            continue
        if c_low >= high:
            break
        if c_low > start:
            parts.append((start, c_low))
        start = max(start, c_high)
    if start < high:
        parts.append((start, high))
    return [(a, b) for a, b in parts if b - a >= WANTED_SPAN_MIN_MM]


def uncovered(lines: list[tuple[float, float, float]], tolerance: float) -> list[list[Range]]:
    """For every line `(radius, low, high)`: the stretches of it (along z) with no line of a smaller radius under them. One sweep from the
    smallest radius up; the ranges of the lines already seen are kept merged."""
    order = sorted(range(len(lines)), key=lambda i: lines[i][0])
    result: list[list[Range]] = [[] for _ in lines]
    covered: list[Range] = []
    position = 0
    while position < len(order):
        group = [order[position]]
        while position + len(group) < len(order) and lines[order[position + len(group)]][0] - lines[group[0]][0] <= tolerance:
            group.append(order[position + len(group)])
        for index in group:
            result[index] = _minus(lines[index][1], lines[index][2], covered)
        covered = _merged(covered + [(lines[index][1], lines[index][2]) for index in group])
        position += len(group)
    return result


def follow_dip(
    curves: TipCurves, start: Point, level: float, top: float, tool: list[ToolLoop], keep: RegionIndex, tolerance: float,
) -> list[Segment]:
    """From `start` (a place on the line at the radius `level`, where the tool stood) along the contour: down as far as the tool may stand (a level
    stretch leads on), but not deeper than one depth of cut (`top - level`) below the line, then up to the radius `top`. When the rise ends on a
    crest below the line, on again down the other side: the dip has more than one hollow. A start that is not on the contour goes down to it first.
    Empty when the contour leads nowhere."""
    floor = level - (top - level)
    moves: list[Segment] = []
    here = start
    for _ in range(TIP_WALK_MAX_PIECES):
        down = tip_walk(curves, here, floor, -1, tool, keep, tolerance, (-1.0, 0.0) if not moves else None, True, moves)
        moves += down
        here = down[-1].end if down else here
        up = tip_walk(curves, here, top, 1, tool, keep, tolerance, None, False, moves)
        moves += up
        here = up[-1].end if up else here
        if not (down or up) or here.x >= level - tolerance:
            break
    return moves
