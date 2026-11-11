"""The tool as loops of edges (`geometry/tool_edges.py`), and the planning copy with the clearance wedge.

The planning copy is for the reach and entry decisions of a roughing step only: its back edge (the trailing cutting edge at the nose) is
turned by the clearance angle of the block towards the part, so a plain collision test keeps the angle that must stay free behind the
tool. The real tool is used for removing material, for the finishing pass and for the checker.
"""

from __future__ import annotations

import math

from ..constants import GEOMETRY_TOLERANCE_MM, NEUTRAL_NOSE_TOLERANCE_DEG, RIGHT_ANGLE_DEG
from ..geometry import LineSegment, Point
from ..geometry.chains import loop_area
from ..geometry.tool_edges import ToolEdge, ToolLoop
from ..tooling.tool import Tool, ToolSegmentRole
from ..tooling.tool_back_angle import back_angle_deg, edge_angle_deg


def tool_loops(tool: Tool) -> list[ToolLoop]:
    """The outline of the tool as a loop of edges (a list of one loop: the geometry takes a list of loops)."""
    return [tuple(ToolEdge(piece.segment, piece.role is ToolSegmentRole.CUTTER) for piece in tool.shape.pieces)]


def back_sides(tool: Tool, free_up: int) -> tuple[int, ...]:
    """The side(s) of the nose where a trailing edge needs room: +1 towards larger Z (right-hand), -1 towards smaller Z
    (left-hand), both for a tool whose nose is symmetric (a neutral tool)."""
    larger, smaller = back_angle_deg(tool, free_up, 1), back_angle_deg(tool, free_up, -1)
    if larger is None and smaller is None:
        return ()
    if larger is not None and smaller is not None and abs(larger - smaller) <= NEUTRAL_NOSE_TOLERANCE_DEG:
        return (1, -1)
    if smaller is None or (larger is not None and larger <= smaller):
        return (1,)
    return (-1,)


def _back_edge(loop: ToolLoop, free_up: int, back: int):
    """(index of the edge, the end at the nose, the far end, its angle from the Z axis) of the trailing edge with the smallest angle."""
    count = len(loop)
    best = None
    for index, edge in enumerate(loop):
        segment = edge.segment
        if not edge.cutting or not isinstance(segment, LineSegment):
            continue
        ends = []
        if loop[index - 1].cutting:
            ends.append((segment.start, segment.end))
        if loop[(index + 1) % count].cutting:
            ends.append((segment.end, segment.start))
        for near, far in ends:
            dx, dz = far.x - near.x, far.z - near.z
            if back * dz <= GEOMETRY_TOLERANCE_MM:
                continue
            angle = edge_angle_deg(dx, dz, free_up, back)
            if -GEOMETRY_TOLERANCE_MM <= angle <= RIGHT_ANGLE_DEG + GEOMETRY_TOLERANCE_MM and (best is None or angle < best[-1]):
                best = (index, near, far, max(angle, 0))
    return best


def planning_loops(tool: Tool, free_up: int, clearance_deg: float) -> list[ToolLoop]:
    """The outline of the tool with its back edge(s) turned by `clearance_deg` towards the part, about the end at the nose: the body
    grows towards a wall behind the tool, so the tool is only accepted where its back edge is steeper than the wall by the clearance.
    The thin wedge between the old and the new edge is closed by a connecting edge that keeps the marking of the old one."""
    loops = tool_loops(tool)
    if clearance_deg <= 0 or not loops:
        return loops
    main = list(loops[0])
    original = tuple(main)
    found = [(edge, back) for back in back_sides(tool, free_up) if (edge := _back_edge(original, free_up, back)) is not None]  # on the outline as it is
    for (index, near, far, angle), back in sorted(found, key=lambda item: -item[0][0]):  # the later edge first: the indices before it stay valid
        length = near.distance_to(far)
        tilted = max(angle - clearance_deg, 0)
        turned = Point(near.x + free_up * length * math.sin(math.radians(tilted)), near.z + back * length * math.cos(math.radians(tilted)))
        edge = main[index]
        if edge.segment.start.is_close(near):  # runs from the nose to the far end: nose -> turned, turned -> far
            pieces = [ToolEdge(LineSegment(near, turned), edge.cutting), ToolEdge(LineSegment(turned, far), edge.cutting)]
        else:  # runs from the far end to the nose: far -> turned, turned -> nose
            pieces = [ToolEdge(LineSegment(far, turned), edge.cutting), ToolEdge(LineSegment(turned, near), edge.cutting)]
        before = abs(_area(main))
        trial = main[:index] + pieces + main[index + 1:]
        if abs(_area(trial)) >= before:  # the copy may only grow: an edge with the body on its far side (a reflected tool) stays as it is
            main = trial
    return [tuple(main), *loops[1:]]


def _area(loop: list[ToolEdge]) -> float:
    return loop_area(tuple(edge.segment for edge in loop))
