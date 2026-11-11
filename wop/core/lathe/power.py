"""Approximate spindle power of a planned program (requirement M4).

The model is the plain specific-cutting-force one: power = kc * A * vc / 60000 kW, divided by an efficiency, with A the cross
section of the chip (depth of cut * feed when turning). It is one sum per block, from the values of its form (the user's wish,
2026-10-23: an estimate needs no replay of the moves), at the place where it is largest: the biggest diameter the block cuts,
where the cutting speed is highest. What each kind of block counts as its chip is in `_chip` (GUESS, see the design notes).
Everything is an estimate and is labelled so. Hand-written blocks and machine functions cut nothing that is known here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..constants import POWER_EFFICIENCY, POWER_FORMULA_DIVISOR, POWER_LABEL, POWER_PEAK_TO_MEAN, THREAD_HALF_ANGLE_DEG
from ..blocks.turning_job import PassDirection
from ..geometry import ArcSegment, Point
from .machine import MachineDef
from ..material import Material
from ..program_model.operations import ArcMove, LinearMove, Rapid, plain_moves
from ..program_model.program import Program, ProgramPlan
from .spindle import cutting_speed_at


@dataclass(frozen=True)
class BlockPower:
    block_index: int
    required_kw: float  # the largest power the block needs (0: nothing cut, or nothing known)
    position: Point | None  # where: at the biggest radius the block cuts


@dataclass(frozen=True)
class PowerEstimate:
    blocks: list[BlockPower] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)  # overloads and reasons why nothing was checked
    label: str = POWER_LABEL

    @property
    def checked(self) -> bool:
        return bool(self.blocks)


def estimate_power(program: Program, plan: ProgramPlan, machine: MachineDef | None, material: Material | None) -> PowerEstimate:
    """Required spindle power per block, and messages for blocks above the machine's power."""
    if material is None:
        name = program.raw_part.material
        return PowerEstimate(messages=[f"power check skipped: material {name!r} is not in the material table"])
    warning = material.power_check_warning()
    if warning is not None:
        return PowerEstimate(messages=[f"{warning}"])
    force = material.specific_cutting_force_n_mm2
    assert force is not None
    available = None if machine is None else machine.spindle_power_kw
    blocks: list[BlockPower] = []
    messages: list[str] = []
    for block_index, block_plan in enumerate(plan.blocks):
        kw, at = _block_power(program, block_plan, force)
        blocks.append(BlockPower(block_index, kw, at))
        if available is not None and kw > available:
            messages.append(
                f"block {block_plan.number} ({block_plan.block.type_name}): needs about {kw:.1f} kW "
                f"({POWER_LABEL}), the spindle has {available:g} kW; reduce the depth of cut or the feed"
            )
    if machine is None or machine.spindle_power_kw is None:
        messages.append("power not compared: the spindle power of the machine is not known")
    return PowerEstimate(blocks, messages)


def _block_power(program: Program, block_plan, force: float) -> tuple[float, Point | None]:
    """The power of one block (kW) and where it is needed: the chip of `_chip` at the cutting speed of its radius."""
    removed = block_plan.result.removed
    bounds = None if removed is None or removed.is_empty else removed.bounds
    if bounds is None:
        return 0.0, None
    chip = _chip(program, block_plan, bounds)
    if chip is None:
        return 0.0, None
    area_mm2, radius = chip
    kw = force * area_mm2 * cutting_speed_at(block_plan.block.spindle, radius) / POWER_FORMULA_DIVISOR / POWER_EFFICIENCY
    return kw, Point(bounds.max_x, bounds.max_z)


def _chip(program: Program, block_plan, bounds) -> tuple[float, float] | None:
    """(the cross section of the chip in mm2, the radius whose cutting speed counts) of the block's biggest cut, or None.

    GUESS (2026-10-23): turning, contour turning and facing: the depth of cut of the form, but no more than the size of what the block
    takes off across the passes, times the feed (a block that only finishes a thin skin is estimated too high: the safe side). Grooving: the cutting edge of the tool (its width along Z), no wider
    than the groove, times the feed. Drilling: half the drill diameter times the feed, at the speed of a quarter of the diameter (the
    textbook drilling formula). Threading: the first pass, a triangle of the first cut depth with the half angle of the thread (the
    compound angle, 30 degrees when it is 0). A custom path: the thickness it takes off (`_thickness`) times its feed. All at the biggest radius the block cuts."""
    block = block_plan.block
    feed = getattr(block, "feed_mm_per_rev", None)
    radius = bounds.max_x
    kind = block.type_name
    if kind in ("turning", "turning_contour", "facing"):
        axial = kind == "facing" or block.pass_direction is PassDirection.ALONG_X  # the depth of cut is along Z
        size = (bounds.max_z - bounds.min_z) if axial else (bounds.max_x - bounds.min_x)
        return min(block.depth_of_cut_mm, size) * feed, radius
    if kind == "grooving":
        cutter = program.tool(block.tool_number).shape.cutter_segments
        edge = max((p.z for s in cutter for p in (s.start, s.end)), default=0.0) - min((p.z for s in cutter for p in (s.start, s.end)), default=0.0)
        width = min(edge, block.width_mm) if edge > 0 else block.width_mm
        return width * feed, radius
    if kind == "drilling":
        cutter = program.tool(block.tool_number).shape.cutter_segments
        drill_radius = max((p.x for s in cutter for p in (s.start, s.end)), default=0.0) or radius
        return drill_radius * feed, drill_radius / 2
    if kind == "threading":
        half_angle = block.compound_angle_deg if block.compound_angle_deg > 0 else THREAD_HALF_ANGLE_DEG
        return block.first_cut_depth_mm ** 2 * math.tan(math.radians(half_angle)), radius
    if kind == "custom_path" and feed:
        return _thickness(block_plan, bounds, False) * feed, radius
    return None


def _thickness(block_plan, bounds, axial: bool) -> float:
    """How thick the material is that a block without a depth of cut takes off: POWER_PEAK_TO_MEAN times its mean thickness (the area
    over the length of the feed moves), but no more than the size of the removed area across the moves (GUESS)."""
    size = (bounds.max_z - bounds.min_z) if axial else (bounds.max_x - bounds.min_x)
    length = _feed_length(block_plan.operations)
    if length <= 0:
        return size
    return min(size, POWER_PEAK_TO_MEAN * block_plan.result.removed.area / length)


def _feed_length(operations) -> float:
    """The length of the feed moves (lines and arcs) of a block."""
    length, here = 0.0, None
    for original in operations:
        for move in plain_moves(original):
            if not isinstance(move, (Rapid, LinearMove, ArcMove)):
                continue
            if here is not None and isinstance(move, LinearMove):
                length += here.distance_to(move.end)
            elif here is not None and isinstance(move, ArcMove) and not here.is_close(move.end):
                length += ArcSegment(here, move.end, move.center, move.direction).length
            here = move.end
    return length
