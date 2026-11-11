"""What the program supplies to the sketch of a custom path: the safe point and the part as it is before the block.

The part is the material the earlier blocks left (`BlockContext.residual`), drawn as locked construction lines and arcs the path can be
dimensioned to. Its pieces are keyed by their place in the outline (`outline/<loop>.<piece>`); when an earlier block changes the number
or kind of the pieces, the sketch drops every relation to the part (`sketch.locked`).
"""

from __future__ import annotations

from ..constants import PATH_OUTLINE_MAX_PIECES, SAFE_POINT_KEY
from ..geometry import ArcSegment, Point
from ..geometry.region import Region
from ..sketch.locked import LockedArc, LockedLine, LockedPoint

OUTLINE_GROUP = "outline"


def path_locked_items(
    safe: Point, residual: Region | None,
) -> tuple[tuple[LockedPoint, ...], tuple[LockedLine, ...], tuple[LockedArc, ...]]:
    """The locked points, lines and arcs of a path sketch. `residual` None (or a part with too many pieces) leaves the part out."""
    points = [LockedPoint(SAFE_POINT_KEY, safe.x, safe.z)]
    lines: list[LockedLine] = []
    arcs: list[LockedArc] = []
    loops = () if residual is None else residual.loops
    if sum(len(loop) for loop in loops) > PATH_OUTLINE_MAX_PIECES:
        loops = ()
    for loop_index, loop in enumerate(loops):
        for index, segment in enumerate(loop):
            key = f"{OUTLINE_GROUP}/{loop_index}.{index}"
            following = f"{OUTLINE_GROUP}/{loop_index}.{(index + 1) % len(loop)}"
            points.append(LockedPoint(key + "s", segment.start.x, segment.start.z))
            if isinstance(segment, ArcSegment):
                points.append(LockedPoint(key + "c", segment.center.x, segment.center.z))
                arcs.append(LockedArc(key, key + "c", key + "s", following + "s", segment.direction))
            else:
                lines.append(LockedLine(key, key + "s", following + "s"))
    return tuple(points), tuple(lines), tuple(arcs)
