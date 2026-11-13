"""What a post may know besides the single operation it writes: the tools, the blocks, the project and the clock.

The whole block list is known before the first line is written, so a template can look ahead (the next tool, the next block).
The clock is an input, so a test can fix it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from ..core.geometry import ArcSegment, Point
from ..core.lathe.machine import MachineDef
from ..core.program_model.operations import (
    ArcMove,
    LinearMove,
    Operation,
    Rapid,
    RapidAxes,
    SetSpindle,
    SpindleMode,
    StopSpindle,
    ToolChange,
    plain_moves,
)
from ..core.constants import DEFAULT_WORK_OFFSET
from ..core.program_model.program import Program, ProgramPlan
from .post_constants import ESTIMATED_RAPID_MM_PER_MIN, M_PER_MIN_TO_MM_PER_MIN, WOP_VERSION_TEXT

DIAMETER_FACTOR = 2


@dataclass(frozen=True)
class ToolInfo:
    number: int
    name: str = ""
    kind: str = ""
    offset_number: int | None = None  # the tool offset of the tool (its number unless the user set another)
    material: str = ""
    nose_radius_mm: float | None = None
    tip_direction: int | None = None  # imaginary tip number 1 to 9; not known yet (compensation, later)


@dataclass(frozen=True)
class BlockInfo:
    number: int  # as the user sees it, 1-based
    name: str = ""
    type_name: str = ""
    tool_number: int | None = None


@dataclass(frozen=True)
class PostContext:
    project_title: str = ""
    machine_name: str = ""
    wop_version: str = WOP_VERSION_TEXT
    material: str = ""
    work_offset: str = DEFAULT_WORK_OFFSET  # G54 ...: the work offset of the project
    part_diameter_mm: float | None = None
    part_length_mm: float | None = None
    tools: dict[int, ToolInfo] = field(default_factory=dict, hash=False)
    blocks: tuple[BlockInfo, ...] = ()
    tool_sequence: tuple[int, ...] = ()  # the tool of every tool change, in the order of the program
    now: datetime = datetime(2000, 1, 1)
    path_length_mm: float = 0
    estimated_time_min: float = 0
    change_radius_mm: float | None = None  # the tool change position of the machine in machine coordinates (X radius, Z); None: none
    change_z_mm: float | None = None
    max_rpm: float | None = None  # the highest spindle speed of the machine (a ramp before a stop with constant surface speed is limited by it)

    @property
    def tools_in_use(self) -> tuple[ToolInfo, ...]:
        """Every tool once, in the order of first use."""
        numbers = list(dict.fromkeys(self.tool_sequence))
        return tuple(self.tools.get(number, ToolInfo(number)) for number in numbers)


def make_context(
    program: Program, plan: ProgramPlan, project_title: str, machine_name: str, now: datetime,
    machine: MachineDef | None = None, work_offset: str = DEFAULT_WORK_OFFSET,
) -> PostContext:
    sequence = tuple(op.tool_number for op in plan.operations if isinstance(op, ToolChange))
    tools = {}
    for number in dict.fromkeys(sequence):
        try:
            tool = program.tool(number)
        except ValueError:  # a tool that is not defined: the planner reports it, the post knows only the number
            continue
        tools[number] = ToolInfo(
            number, tool.name, tool.kind, number if tool.offset_number is None else tool.offset_number, tool.material.value, tool.nose_radius_mm,
        )
    blocks = tuple(
        BlockInfo(bp.number, bp.block.title, bp.block.type_name, bp.block.tool_number if bp.block.needs_tool else None)
        for bp in plan.blocks
    )
    raw = program.raw_part
    speeds = (None, None) if machine is None else (machine.max_velocity_x_mm_min, machine.max_velocity_z_mm_min)
    length, minutes = _path_summary(plan.operations, speeds)
    return PostContext(
        project_title=project_title, machine_name=machine_name, wop_version=WOP_VERSION_TEXT,
        material=raw.material, work_offset=work_offset, part_diameter_mm=raw.outer_diameter_mm, part_length_mm=raw.length_mm,
        tools=tools, blocks=blocks, tool_sequence=sequence, now=now, path_length_mm=length, estimated_time_min=minutes,
        change_radius_mm=None if machine is None else machine.machine_change_radius_mm,
        change_z_mm=None if machine is None else machine.machine_change_z_mm,
        max_rpm=None if machine is None else machine.max_rpm,
    )


def _rpm(setting, radius: float) -> float | None:
    if setting is None:
        return None
    if setting.mode is SpindleMode.CONSTANT_RPM:
        return setting.value
    if radius <= 0:
        return setting.rpm_limit
    rpm = setting.value * M_PER_MIN_TO_MM_PER_MIN / (math.pi * DIAMETER_FACTOR * radius)
    return rpm if setting.rpm_limit is None else min(rpm, setting.rpm_limit)


def _rapid_minutes(start: Point, end: Point, speeds: tuple[float | None, float | None]) -> float:
    """A rapid at the fastest speed of the machine: both axes move together, the slower one decides. Without the speeds of the
    machine a fixed rate (a GUESS)."""
    x_speed, z_speed = speeds
    if x_speed and z_speed:
        return max(abs(end.x - start.x) / x_speed, abs(end.z - start.z) / z_speed)
    return start.distance_to(end) / ESTIMATED_RAPID_MM_PER_MIN


def _path_summary(operations: list[Operation], speeds: tuple[float | None, float | None]) -> tuple[float, float]:
    """The length of all moves (mm) and an estimate of the time (minutes): feed moves at feed times speed, rapids at the
    maximum speed of the machine (the machine has no separate rapid speed yet); tool changes, stops and dwells are not counted."""
    length = minutes = 0.0
    position: Point | None = None
    spindle = None
    for operation in operations:
        for move in plain_moves(operation):
            if isinstance(move, SetSpindle):
                spindle = move.setting
            elif isinstance(move, StopSpindle):
                spindle = None
            elif isinstance(move, RapidAxes):
                if position is not None:
                    target = Point(position.x if move.x is None else move.x, position.z if move.z is None else move.z)
                    length += position.distance_to(target)
                    minutes += _rapid_minutes(position, target, speeds)
                    position = target
            elif isinstance(move, (Rapid, LinearMove, ArcMove)):
                if position is not None:
                    if isinstance(move, ArcMove):
                        travelled = ArcSegment(position, move.end, move.center, move.direction).length
                    else:
                        travelled = position.distance_to(move.end)
                    length += travelled
                    if isinstance(move, Rapid):
                        minutes += _rapid_minutes(position, move.end, speeds)
                    else:
                        rpm = _rpm(spindle, move.end.x)
                        if rpm:
                            minutes += travelled / (move.feed_mm_per_rev * rpm)
                position = move.end
    return length, minutes
