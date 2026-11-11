"""The back angle of a tool: how steeply its trailing cutting edge leaves the nose, measured from the Z axis.

A tool that goes into a pocket has its body behind the nose. The material behind the pocket is a wall that rises
from the nose; the body fits above that wall only when the trailing edge of the tool is steeper than the wall.
A CNMG insert at 95 degrees has a trailing edge of 5 degrees (it fits behind nothing but a flat), a 35 degree V
insert at 72.5 degrees has one of 72.5 degrees.

The angle is worked out from the cutting edges of the tool shape (an insert from its entries, a drawn tool from its
contour): the straight cutting edges at the nose that run backwards from it, the smallest angle counts. `free_up` is +1
when the tool lies towards larger X than the contour (outside turning) and -1 when it lies towards smaller X (a bore);
`back` is +1 when the body of the tool lies towards larger Z (a right-hand tool) and -1 for a left-hand tool.
"""

from __future__ import annotations

import math

from ..constants import GEOMETRY_TOLERANCE_MM, NEUTRAL_NOSE_TOLERANCE_DEG, RIGHT_ANGLE_DEG
from ..geometry import LineSegment
from .tool import Tool, ToolSegmentRole


def edge_angle_deg(dx: float, dz: float, free_up: int, back: int) -> float:
    """The angle from the Z axis of a direction (dx, dz): 0 along the axis towards the back, 90 straight towards the free
    side, more than 90 leaning forwards."""
    return math.degrees(math.atan2(free_up * dx, back * dz))


def back_angle_deg(tool: Tool, free_up: int = 1, back: int = 1) -> float | None:
    """The trailing edge angle of the tool; None when the cutting edges have no straight edge that runs backwards from
    the nose. The nose edges are the straight cutting edges that join another cutting edge (the nose arc, or the other
    edge at a sharp corner): the tip does not have to lie on the tool for this, so a tool whose reference point is far
    from its nose works too."""
    pieces = tool.shape.pieces
    count = len(pieces)
    found: list[float] = []
    for index, piece in enumerate(pieces):
        segment = piece.segment
        if piece.role is not ToolSegmentRole.CUTTER or not isinstance(segment, LineSegment):
            continue
        ends = []  # (the end that joins another cutting edge, the other end)
        if pieces[index - 1].role is ToolSegmentRole.CUTTER:
            ends.append((segment.start, segment.end))
        if pieces[(index + 1) % count].role is ToolSegmentRole.CUTTER:
            ends.append((segment.end, segment.start))
        for near, far in ends:
            dx, dz = far.x - near.x, far.z - near.z
            if back * dz <= GEOMETRY_TOLERANCE_MM:  # runs forward or across: not a back edge
                continue
            angle = edge_angle_deg(dx, dz, free_up, back)
            if -GEOMETRY_TOLERANCE_MM <= angle <= RIGHT_ANGLE_DEG + GEOMETRY_TOLERANCE_MM:
                found.append(max(angle, 0))
    return min(found) if found else None


def back_direction(tool: Tool) -> int:
    """+1 when the body of the tool lies towards larger Z than its tip (a right-hand tool), -1 when it lies towards smaller Z.
    A tool with a symmetric nose (a 35 degree V pointing straight at the axis) has a back edge on both sides at the same angle:
    it has no hand, whichever side its body is heavier on, and counts as right-hand (the way the program cuts)."""
    towards_larger_z, towards_smaller_z = back_angle_deg(tool, 1, 1), back_angle_deg(tool, 1, -1)
    if towards_larger_z is not None and towards_smaller_z is not None and abs(towards_larger_z - towards_smaller_z) <= NEUTRAL_NOSE_TOLERANCE_DEG:
        return 1
    points = [point for piece in tool.shape.pieces for point in (piece.segment.start, piece.segment.end)]
    return 1 if sum(point.z for point in points) >= 0 else -1
