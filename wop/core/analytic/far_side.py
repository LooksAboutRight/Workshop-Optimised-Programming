"""A tool that works on the far side of the axis (back boring: the left-hand boring bar on the far wall of a bore, with the spindle reversed).

The part is round, so the far wall is the mirror image of the near wall. A block with such a tool is planned as its mirror image: with
the tool turned over the axis (it becomes the usual tool of the near wall), and the moves are then turned over the axis again, so the
machine moves at negative X. The material the block removes is the same on both sides and is kept as it is (the residual of the program
is the half profile above the axis). Which side a tool works on is told by its body: an outside tool has its body towards larger X from
the tip, an inside tool (a bar towards the axis) towards smaller X; the other way round is the far side.
"""

from __future__ import annotations

from dataclasses import replace

from ..blocks.base import Safety
from ..constants import GEOMETRY_TOLERANCE_MM
from ..geometry import Point
from ..program_model.operations import Operation
from ..tooling.tool import Tool
from . import mirror


def body_side(tool: Tool) -> int:
    """+1 when the body of the tool (its holder pieces) lies towards larger X than its tip, -1 towards smaller X, 0 when it lies on the axis of
    the tip (a tool with no holder, or one centred on the tip)."""
    ends = [point.x for segment in tool.shape.holder_segments for point in (segment.start, segment.end)]
    middle = sum(ends) / len(ends) if ends else 0.0
    return 1 if middle > GEOMETRY_TOLERANCE_MM else -1 if middle < -GEOMETRY_TOLERANCE_MM else 0


def works_on_far_side(tool: Tool, inside: bool) -> bool:
    """True when the tool, with its tip at the origin, stands the other way round than a tool of that side normally does."""
    side = body_side(tool)
    return side != 0 and side == (1 if inside else -1)


def turned_tool(tool: Tool) -> Tool:
    """The tool turned over the axis: the tool of the near wall that the far side is planned with."""
    return mirror.MIRROR_X.tool(tool)


def turned_safety(safety: Safety) -> Safety:
    """The safe positions as the turned block sees them: the safe radius turned over the axis, so that the block begins and ends at the real
    safe point once its moves are turned back (and not at the safe point below the axis)."""
    return replace(safety, safe_radius_mm=-safety.safe_radius_mm)


def turned_operations(operations: tuple[Operation, ...]) -> tuple[Operation, ...]:
    """The moves turned over the axis (arcs turn the other way round; the spindle and the block markers stay)."""
    return tuple(mirror.MIRROR_X.operation(operation) for operation in operations)


def turned_point(at: Point | None) -> Point | None:
    return None if at is None else mirror.MIRROR_X.point(at)


def turned_result(result):
    """A block result planned with the turned tool, in the machine's coordinates."""
    return replace(result, operations=turned_operations(result.operations))
