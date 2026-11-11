"""Shapes of the ready-made tools (requirement T2). The tool types (`tool_types`) call these."""

from __future__ import annotations

from ..constants import (
    THREAD_FLANK_HALF_ANGLE_DEG,
    THREAD_TOOL_HOLDER_LENGTH_MM,
    THREAD_TOOL_TIP_HEIGHT_MM,
    DRILL_TOOL_DIAMETER_MM,
    DRILL_TOOL_FLUTE_LENGTH_MM,
    DRILL_TIP_ANGLE_DEG,
    FLAT_ANGLE_DEG,
    DRILL_TOOL_SHANK_LENGTH_MM,
    HALF,
    GROOVE_TOOL_BLADE_REACH_MM,
    GROOVE_TOOL_BLADE_WIDTH_MM,
    GROOVE_TOOL_HOLDER_LENGTH_MM,
    GROOVE_TOOL_HOLDER_WIDTH_MM,
    STARTER_TOOL_HEIGHT_MM,
    STARTER_TOOL_WIDTH_MM,
)
import math

from ..geometry import LineSegment, Point
from .tool import Tool, ToolError, ToolSegment, ToolSegmentRole, ToolShape


def block_tool(number: int, name: str, body_towards_larger_x: bool = True) -> Tool:
    """A plain rectangular tool with its tip at the origin.

    body_towards_larger_x=True is an outside tool (body away from the axis),
    False a boring bar (body towards the axis). The edges at the tip cut, the
    other two are holder.
    """
    side = 1 if body_towards_larger_x else -1
    width, height = STARTER_TOOL_WIDTH_MM * side, STARTER_TOOL_HEIGHT_MM
    corners = [Point(0, 0), Point(width, 0), Point(width, height), Point(0, height), Point(0, 0)]
    roles = [
        ToolSegmentRole.CUTTER,
        ToolSegmentRole.HOLDER,
        ToolSegmentRole.HOLDER,
        ToolSegmentRole.CUTTER,
    ]
    pieces = tuple(
        ToolSegment(LineSegment(a, b), role)
        for (a, b), role in zip(zip(corners, corners[1:]), roles)
    )
    return Tool(number, name, ToolShape(pieces))


def groove_tool(
    number: int,
    name: str,
    blade_width_mm: float = GROOVE_TOOL_BLADE_WIDTH_MM,
    reach_mm: float = GROOVE_TOOL_BLADE_REACH_MM,
    body_towards_larger_x: bool = True,
) -> Tool:
    """A grooving tool: a thin blade with the cutting edge across Z, then a wider holder.

    The tip is the corner of the cutting edge with the smaller Z; the tool lies
    on the larger-Z side of it. The edge at the tip is the only cutter.
    """
    side = 1 if body_towards_larger_x else -1
    width = blade_width_mm
    wide = GROOVE_TOOL_HOLDER_WIDTH_MM
    length = reach_mm + GROOVE_TOOL_HOLDER_LENGTH_MM
    reach = reach_mm * side
    corners = [
        Point(0, 0), Point(0, width), Point(reach, width), Point(reach, wide),
        Point(length * side, wide), Point(length * side, 0), Point(reach, 0), Point(0, 0),
    ]
    # The blade (edge and both side faces up to the reach) works inside the groove, so it
    # counts as cutter; only the wider holder behind it must stay out of the material.
    cutter, holder = ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER
    roles = [cutter, cutter, holder, holder, holder, holder, cutter]
    pieces = tuple(
        ToolSegment(LineSegment(a, b), role)
        for (a, b), role in zip(zip(corners, corners[1:]), roles)
    )
    return Tool(number, name, ToolShape(pieces))


def drill_tool(
    number: int,
    name: str,
    diameter_mm: float = DRILL_TOOL_DIAMETER_MM,
    flute_length_mm: float = DRILL_TOOL_FLUTE_LENGTH_MM,
    tip_angle_deg: float = DRILL_TIP_ANGLE_DEG,
) -> Tool:
    """A drill on the spindle axis: the point at the origin, the body towards larger Z.

    The cone of the point, the flutes and the axis edge count as cutter (the axis edge
    has nothing to collide with); the shank behind the flutes is the holder.
    """
    if diameter_mm <= 0 or flute_length_mm <= 0:
        raise ToolError("a drill needs a diameter and a length")
    if not 0 < tip_angle_deg <= FLAT_ANGLE_DEG:
        raise ToolError("the tip angle must be between 0 and 180 degrees")
    radius = diameter_mm / 2
    cone = radius / math.tan(math.radians(tip_angle_deg) * HALF)
    if cone >= flute_length_mm:
        raise ToolError("the drill is shorter than its point")
    top = flute_length_mm + DRILL_TOOL_SHANK_LENGTH_MM
    corners = [Point(0, 0), Point(radius, cone), Point(radius, flute_length_mm), Point(radius, top), Point(0, top), Point(0, 0)]
    cutter, holder = ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER
    roles = [cutter, cutter, holder, holder, cutter]
    pieces = tuple(
        ToolSegment(LineSegment(a, b), role)
        for (a, b), role in zip(zip(corners, corners[1:]), roles)
    )
    return Tool(number, name, ToolShape(pieces))


def thread_tool(number: int, name: str, body_towards_larger_x: bool = True) -> Tool:
    """A 60 degree threading tool: a V point at the origin, both flanks cut, holder behind."""
    side = 1 if body_towards_larger_x else -1
    height = THREAD_TOOL_TIP_HEIGHT_MM
    half = height * math.tan(math.radians(THREAD_FLANK_HALF_ANGLE_DEG))
    length = height + THREAD_TOOL_HOLDER_LENGTH_MM
    corners = [
        Point(0, 0), Point(height * side, half), Point(length * side, half),
        Point(length * side, -half), Point(height * side, -half), Point(0, 0),
    ]
    cutter, holder = ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER
    roles = [cutter, holder, holder, holder, cutter]
    pieces = tuple(
        ToolSegment(LineSegment(a, b), role)
        for (a, b), role in zip(zip(corners, corners[1:]), roles)
    )
    return Tool(number, name, ToolShape(pieces))
