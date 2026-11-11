"""The first step of a roughing plan: the parallel lines that are to be cut, with no tool in mind (types, the region to remove, the stretches of a line).

From the material that is there, the finished contour and the finishing allowance, the region to remove is worked out with the
trim-and-link boolean (`chains.py`). Lines are then laid through it at the depth-of-cut spacing, along Z or across X, and every
line is cut where it crosses the border of the region: the stretches inside are the places to cut (`spans`). Which stretches are
pockets, and the plan as a whole, are in `pockets.py` and `wanted_plan.py`. Nothing here knows a tool, the hand of a tool, or
whether the block is inside or outside, except the side the free air is on, which says in which direction the levels run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from ..constants import CHAIN_SNAP_MM, GEOMETRY_TOLERANCE_MM, WANTED_SPAN_MIN_MM
from ..geometry.offset import offset_segments
from ..geometry import LineSegment, Point, Segment
from ..geometry.chains import ChainError, Loop, closed_loop, crossings, oriented
from ..geometry.tidy import steady_intersection


class LineDirection(Enum):
    ALONG_Z = "along Z"  # the lines run along Z, one after the other at smaller and smaller radius (outside)
    ALONG_X = "across X"  # the lines run across, one after the other at smaller and smaller Z


class LineKind(Enum):
    OPEN = "open"  # at least one end is open air: the line can be entered along itself
    POCKET = "pocket"  # both ends are walls: the line is entered from above, with the plunge depth of cut


@dataclass(frozen=True)
class WantedLine:
    """One stretch to cut: `high` and `low` are its ends (the larger and the smaller coordinate along the line)."""

    level_number: int  # the number of the normal level (-1 for a pocket line: those are spaced by the plunge depth of cut)
    high: Point
    low: Point
    kind: LineKind = LineKind.OPEN
    open_high: bool = True  # the high end is open air (not a wall of material that stays)
    open_low: bool = False
    pocket: int = -1  # the number of the pocket (pocket lines)
    layer: int = -1  # 0 for the first layer of its pocket, then 1, 2 ... (pocket lines)


@dataclass(frozen=True)
class WantedPlan:
    removal: tuple[Loop, ...]  # the region to remove, as closed loops of lines and arcs
    lines: tuple[WantedLine, ...]


# --- the region to remove ------------------------------------------------------------------------

def front_floor(path: list[Segment], outside: bool, allowance: float, start_z: float) -> float | None:
    """The radius of the floor that closes the region in front of the contour (the material in front of its start is removed down to the
    radius where the contour plus allowance begins), or None when the contour starts at the front of the material."""
    tol = GEOMETRY_TOLERANCE_MM
    dropped = 0
    while dropped < len(path) - 1 and all(abs(p.z - start_z) <= tol for p in (path[dropped].start, path[dropped].end)):
        dropped += 1
    if allowance > tol:
        first = next(segment for index, segment in offset_segments(list(enumerate(path)), -allowance if outside else allowance, closed=False) if index >= dropped).start
    else:
        first = path[dropped].start
    return first.x if start_z - first.z > tol else None


def removal_loops(
    path: list[Segment], stock: list[Loop], outside: bool, allowance: float, outer: float, start_z: float,
    cleaned_stock: Callable[[], list[Loop]] | None = None,
) -> list[Loop]:
    """The material between the stock and the contour moved away from the part by the allowance.

    `path` is the contour from the front to the chuck (with the wall at its end already added), `outer` the radius beyond
    the material where the area is closed again, `start_z` the front of the material. `cleaned_stock`: another version of the
    stock to try when the exact one cannot be joined (see `material.chains_of_region`)."""
    area = [oriented(closed_loop(removal_ring(path, outside, allowance, outer, start_z)), True)]
    try:
        return steady_intersection(stock, area, CHAIN_SNAP_MM)
    except ChainError:
        if cleaned_stock is None:
            raise
        return steady_intersection(cleaned_stock(), area, CHAIN_SNAP_MM)


def removal_ring(path: list[Segment], outside: bool, allowance: float, outer: float, start_z: float) -> list[Segment]:
    """The border of the area beyond the contour moved away from the part by the allowance, as a closed chain: the contour (without its
    first lines that lie on the front `start_z`), out to `outer` at its end, back along the front and down to where it begins."""
    tol = GEOMETRY_TOLERANCE_MM
    dropped = 0  # first lines of the contour that lie on the front of the material: they do not bound the area
    while dropped < len(path) - 1 and all(abs(p.z - start_z) <= tol for p in (path[dropped].start, path[dropped].end)):
        dropped += 1
    if allowance > tol:
        tagged = offset_segments(list(enumerate(path)), -allowance if outside else allowance, closed=False)
        pieces = [segment for index, segment in tagged if index >= dropped]
    else:
        pieces = list(path[dropped:])
    first, last = pieces[0].start, pieces[-1].end
    head = [LineSegment(Point(first.x, start_z), first)] if start_z - first.z > tol else []
    corner = Point(first.x, start_z) if head else first
    ring = [
        *head, *pieces,
        LineSegment(last, Point(outer, last.z)),
        LineSegment(Point(outer, last.z), Point(outer, start_z)),
        LineSegment(Point(outer, start_z), corner),
    ]
    return [segment for segment in ring if segment.start.distance_to(segment.end) > tol]


# --- lines through a region --------------------------------------------------------------------

def spans(loops: list[Loop], level: float, axis: int) -> list[tuple[float, float]]:
    """The stretches of the line inside the region (even-odd), the ones shorter than the sliver limit left out.
    `axis` 0: a line at constant radius, 1: a line at constant Z."""
    values = crossings(loops, level, axis)
    pairs = zip(values[0::2], values[1::2])
    return [(low, high) for low, high in pairs if high - low >= WANTED_SPAN_MIN_MM]
