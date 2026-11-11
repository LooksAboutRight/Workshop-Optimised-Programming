"""Step B: how far the tool can really go along a wanted line, and the ride up along the contour at its end.

The part and its allowance are the region the planning tool (the tool with the clearance wedge, `tool_edges.planning_loops`) may not
penetrate. The places where it may stand along a stretch of a line come from the two ends, or, when the tool does not fit at an end,
from the places where tool and part touch (`contacts.free_intervals`, exact); the stretch is cut back to them. A stretch with no free place is dropped. Where the tool stops
because its nose touches the contour, it does not stop there: it rides up along the contour, tangent to it, until its tip is as
high as the line above, or until it leaves the material (the walk along the contact curves of `tip_walk.py`).
"""

from __future__ import annotations

from ..constants import CUT_END_SNAP_MM, GEOMETRY_TOLERANCE_MM, WANTED_SPAN_MIN_MM
from ..geometry.offset import offset_segments
from ..geometry import LineSegment, Point, Segment
from ..geometry.chains import Loop, closed_loop, crossing_value, monotone, oriented
from ..geometry.contacts import free_intervals
from ..geometry.penetration import RegionIndex, blocked_by_part
from .tip_walk import TipCurves, tip_walk
from ..geometry.tool_edges import ToolLoop


def keep_loops(path: list[Segment], outside: bool, allowance: float, outer: float, inner: float, far_z: float) -> list[Loop]:
    """The part and its allowance as a closed loop: the contour moved away from the part by the allowance, closed through the chuck
    side (`far_z`), the free side (`outer`) and the axis side (`inner`)."""
    pieces = [segment for _index, segment in offset_segments(list(enumerate(path)), -allowance if outside else allowance, closed=False)] if allowance > GEOMETRY_TOLERANCE_MM else list(path)
    first, last = pieces[0].start, pieces[-1].end
    ring = [
        *pieces,
        LineSegment(last, Point(outer, last.z)),
        LineSegment(Point(outer, last.z), Point(outer, far_z)),
        LineSegment(Point(outer, far_z), Point(inner, far_z)),
        LineSegment(Point(inner, far_z), Point(inner, first.z)),
        LineSegment(Point(inner, first.z), first),
    ]
    return [oriented(closed_loop([s for s in ring if s.start.distance_to(s.end) > GEOMETRY_TOLERANCE_MM]), True)]


def _tip(level: float, along: float, axis: int) -> Point:
    return Point(level, along) if axis == 0 else Point(along, level)


def _blocked(tool: list[ToolLoop], keep: RegionIndex, level: float, along: float, axis: int, tolerance: float) -> bool:
    return blocked_by_part(tool, keep, _tip(level, along, axis), tolerance)


def exact_intervals(
    tool: list[ToolLoop], keep: RegionIndex, level: float, low: float, high: float, tolerance: float,
) -> list[tuple[float, float]]:
    """The stretches of the line at `level` (along Z, from `low` to `high`) where the tool may stand, from the places where tool and part touch
    (`contacts.free_intervals`): exact, with no scan. Stretches shorter than the sliver limit are left out."""
    found = free_intervals(tool, keep, Point(level, high), (0.0, -1.0), high - low, tolerance, WANTED_SPAN_MIN_MM)
    return sorted(((high - s1, high - s0) for s0, s1 in found), reverse=True)


def tip_contact(curve: list[Segment], level: float, low: float, high: float) -> float | None:
    """Where the tool tip, going along the line at `level` from `high` towards `low`, first meets the curve of the tool tip (the contour
    moved by the nose radius and the allowance): the highest crossing in the stretch. None when the line does not meet it."""
    found = []
    for piece in curve:
        for part in monotone(piece, 0):
            if (part.start.x > level + GEOMETRY_TOLERANCE_MM) != (part.end.x > level + GEOMETRY_TOLERANCE_MM):
                z = crossing_value(part, level, 0)
                if low - GEOMETRY_TOLERANCE_MM <= z <= high + GEOMETRY_TOLERANCE_MM:
                    found.append(z)
    return max(found, default=None)


def _snapped(intervals: list[tuple[float, float]], low: float, high: float) -> list[tuple[float, float]]:
    """The ends of the stretches that lie within `CUT_END_SNAP_MM` of an end of the wanted stretch are put on it."""
    return [
        (low if abs(a - low) <= CUT_END_SNAP_MM else a, high if abs(b - high) <= CUT_END_SNAP_MM else b) for a, b in intervals
    ]


def end_intervals(
    tool: list[ToolLoop], keep: RegionIndex, curve: list[Segment], level: float, low: float, high: float, tolerance: float,
) -> tuple[list[tuple[float, float]], bool]:
    """The stretch where the tool may stand, from the two ends only: the end is where the nose touches the contour (`tip_contact`),
    the start is the high end; the planning tool is tested at both. Returns the intervals and whether this fast way was enough
    (False: the tool does not fit at one of the places, so the exact search of `exact_intervals` is used)."""
    contact = tip_contact(curve, level, low, high)
    end = low if contact is None else max(contact, low)
    if end > high - WANTED_SPAN_MIN_MM:
        return [], True
    if _blocked(tool, keep, level, high, 0, tolerance) or _blocked(tool, keep, level, end, 0, tolerance):
        return _snapped(exact_intervals(tool, keep, level, low, high, tolerance), low, high), False
    return _snapped([(end, high)], low, high), True


def ride_up(
    curves: TipCurves, end: Point, goal: float, free_up: int, tool: list[ToolLoop], keep: RegionIndex, tolerance: float, heading: tuple[float, float] | None = None,
) -> list[Segment]:
    """From the end of a line (the tool tip at `end`, touching the part) up along the part to the height `goal` (a radius), as far as the
    planning tool may stand: the walk of `tip_walk.py`, whatever part of the tool touches (`heading`: the direction of the line, to go on to the
    wall when the tool does not touch yet). Empty when no way leads up."""
    return tip_walk(curves, end, goal, free_up, tool, keep, tolerance, heading)


def ride_over(
    curves: TipCurves, ride: list[Segment], level: float, goal: float, tool: list[ToolLoop], keep: RegionIndex, tolerance: float,
) -> list[Segment]:
    """The way over the top of a bump the ride up (`ride`) could not get over because the bump is lower than `goal`: on along the part and
    down to the radius `level` on the other side. Empty when the ride up reached the goal (a wall), or does not get down again."""
    if not ride or goal - ride[-1].end.x <= tolerance:
        return []
    over = tip_walk(curves, ride[-1].end, level, -1, tool, keep, tolerance, flat=True, avoid=ride)
    return over if over and over[-1].end.x <= level + tolerance else []
