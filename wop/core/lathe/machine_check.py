"""Check a planned program against the machine definition (requirement M3)."""

from __future__ import annotations

from ..constants import GEOMETRY_TOLERANCE_MM
from ..geometry import Point
from .machine import Capability, MachineDef, check_extents, check_feed_speed, check_rpm
from ..program_model.operations import ArcMove, DrillOperation, LinearMove, Rapid, SetSpindle, SpindleMode, ThreadOperation
from ..program_model.program import Program, ProgramPlan
from .spindle import rpm_at


def required_capabilities(block) -> set[Capability]:
    """What the machine must be able to do for a block: its type and its spindle mode (a coolant is only a code: the machine just does not act on it when it has none)."""
    needed = set(block.required_capabilities)
    if block.spindle.mode is SpindleMode.CONSTANT_SURFACE_SPEED:
        needed.add(Capability.CONSTANT_SURFACE_SPEED)
    return needed


def check_against_machine(program: Program, plan: ProgramPlan, machine: MachineDef) -> list[str]:
    """Messages for sizes and spindle speeds the machine cannot do."""
    raw = program.raw_part
    messages = check_extents(machine, raw.outer_diameter_mm / 2, raw.length_outside_mm)
    for block_plan in plan.blocks:
        block = block_plan.block
        for capability in sorted(required_capabilities(block) - machine.capabilities, key=lambda c: c.value):
            messages.append(f"block {block_plan.number} ({block.type_name}): the machine has no {capability.value}")
        radii = [
            op.end.x for op in block_plan.operations if isinstance(op, (LinearMove, ArcMove))
        ]
        settings = [block.spindle]
        for op in block_plan.operations:  # a block may change the speed itself (finishing speed)
            if isinstance(op, SetSpindle) and op.setting not in settings:
                settings.append(op.setting)
        found: list[str] = []
        for setting in settings:
            if setting.mode is SpindleMode.CONSTANT_RPM or not radii:
                speeds = [rpm_at(setting, 0)] if setting.mode is SpindleMode.CONSTANT_RPM else []
            else:
                speeds = [rpm_at(setting, max(radii))]  # the lowest speed is at the largest radius
            for rpm in speeds:
                found += [text for text in check_rpm(machine, rpm) if text not in found]
        messages += [f"block {block_plan.number} ({block.type_name}): {text}" for text in found]
        slow = _feed_too_fast(block_plan, machine)
        if slow:
            messages.append(f"block {block_plan.number} ({block.type_name}): {slow}; lower the feed or the spindle speed")
    return messages


def _feed_too_fast(block_plan, machine: MachineDef) -> str:
    """The first feed move of the block that is faster than an axis can go (feed per revolution times the highest
    spindle speed on the move); empty text if none, or if the machine's velocities are not known. Arcs count as
    moving along both axes at the full speed."""
    if machine.max_velocity_x_mm_min is None and machine.max_velocity_z_mm_min is None:
        return ""
    setting = block_plan.block.spindle
    position: Point | None = None
    for op in block_plan.operations:
        if isinstance(op, SetSpindle):
            setting = op.setting  # the speed the following moves are made at
            continue
        if isinstance(op, (DrillOperation, ThreadOperation)):  # feed per revolution along Z at the speed of the axis
            feed = op.feed_mm_per_rev if isinstance(op, DrillOperation) else op.pitch_mm
            rpm = rpm_at(setting, 0 if isinstance(op, DrillOperation) else op.start_x)
            found = check_feed_speed(machine, feed * rpm, 0.0, 1.0)
            if found:
                return f"{feed:g} mm/rev at {rpm:.0f} RPM: {found[0]}"
            position = None
            continue
        end = getattr(op, "end", None)
        if not isinstance(end, Point):
            position = None  # moves along one axis only: the start of the next move is not known
            continue
        if isinstance(op, (LinearMove, ArcMove)) and position is not None:
            rpm = rpm_at(setting, min(position.x, end.x))  # the spindle is fastest at the smallest radius
            speed = op.feed_mm_per_rev * rpm
            if isinstance(op, LinearMove):
                length = position.distance_to(end)
                if length < GEOMETRY_TOLERANCE_MM:
                    position = end
                    continue
                x_share, z_share = abs(end.x - position.x) / length, abs(end.z - position.z) / length
            else:
                x_share = z_share = 1.0
            found = check_feed_speed(machine, speed, x_share, z_share)
            if found:
                return f"{op.feed_mm_per_rev:g} mm/rev at {rpm:.0f} RPM: {found[0]}"
        position = end if isinstance(op, (Rapid, LinearMove, ArcMove)) else None
    return ""
