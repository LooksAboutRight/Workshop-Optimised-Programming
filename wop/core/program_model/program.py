"""A program: raw part, tools and an ordered list of blocks (requirement B1).

plan_program() runs the blocks one after the other. It adds what lies
between blocks (safe retract, tool change, spindle and coolant changes),
follows the residual material, and returns the neutral operation list.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Collection

from ..contour import Contour
from ..blocks.base import NO_CONTOUR, Block, BlockContext, BlockError, BlockResult, Safety
from .operations import (
    BlockBegin,
    CoolantMode,
    Operation,
    Rapid,
    SetCoolant,
    SetSpindle,
    SpindleSetting,
    StopSpindle,
    ToolChange,
    spindle_after,
)
from ..geometry import Point
from .raw_part import RawPart
from ..geometry.region import Region
from ..reach import program_jaws
from .stock import stock_region
from ..constants import NO_TOOL_NUMBER
from ..tooling.stand_in import stand_in_tool
from ..tooling.tool import Tool
from .cutoff import split_off
from .plan_cache import CachedBlock, PlanCache
from ..lathe.workholding import GripMode, Workholding, raw_part_notes, workholding_notes
from ..tooling.tool_reference import with_tip_at_origin
from ..analytic.far_side import turned_result, turned_safety, turned_tool


@dataclass(frozen=True)
class Program:
    raw_part: RawPart
    tools: tuple[Tool, ...]
    safety: Safety
    blocks: tuple[Block, ...] = ()
    contours: tuple[Contour, ...] = ()  # shared by the blocks that refer to them (C5)
    workholding: Workholding | None = None  # chuck and jaws; None: the flat clamping plane (R6)
    toolbox_library: str = ""  # the toolbox the tools came from (T17): its library and name; empty: none
    toolbox_name: str = ""

    def contour(self, contour_id: str) -> Contour:
        for contour in self.contours:
            if contour.contour_id == contour_id:
                return contour
        raise BlockError(f"contour {contour_id!r} does not exist")

    def with_contour(self, contour: Contour) -> "Program":
        """Add the contour, or replace the one with the same id (all blocks follow)."""
        others = tuple(c for c in self.contours if c.contour_id != contour.contour_id)
        known = [c.contour_id for c in self.contours]
        if contour.contour_id in known:
            index = known.index(contour.contour_id)
            return replace(self, contours=others[:index] + (contour,) + others[index:])
        return replace(self, contours=others + (contour,))

    def contour_problem(self, block: Block) -> str:
        """Why a block cannot be planned because of its contour (C10); empty text if all is well."""
        for contour_id in block.contour_ids:
            if contour_id == NO_CONTOUR:
                return "no contour set"
            known = [c for c in self.contours if c.contour_id == contour_id]
            if not known:
                return f"contour {contour_id!r} does not exist"
            if not known[0].is_valid:
                return f"contour {known[0].name} is not valid ({known[0].error or 'no segments'})"
        return block.own_problem()

    def without_contour(self, contour_id: str) -> "Program":
        """Remove a contour; refused while a block still refers to it."""
        users = [b.name or b.block_id for b in self.blocks if contour_id in b.contour_ids]
        if users:
            raise BlockError(f"contour {contour_id!r} is used by: {', '.join(users)}")
        return replace(self, contours=tuple(c for c in self.contours if c.contour_id != contour_id))

    def tool(self, number: int) -> Tool:
        if number == NO_TOOL_NUMBER:
            raise BlockError("no tool chosen")
        for tool in self.tools:
            if tool.number == number:
                return tool
        raise BlockError(f"tool T{number} is not defined")

    def equipped_tool(self, number: int) -> Tool:
        """The tool with its reference point (the touch-off point) at the origin: this is what the checks, the pictures
        and the block planners use."""
        if number == NO_TOOL_NUMBER:  # a block that needs no tool (a machine function) is still planned with a tool
            return with_tip_at_origin(stand_in_tool())
        return with_tip_at_origin(self.tool(number))


class PlanningStopped(Exception):
    """The planning (or the check) was asked to stop between two blocks (`should_stop`): a newer program is waiting. Not a
    `ValueError`, so that no block takes it for its own failure."""


def stop_if_asked(should_stop: Callable[[], bool] | None) -> None:
    if should_stop is not None and should_stop():
        raise PlanningStopped()


@dataclass(frozen=True)
class BlockPlan:
    block: Block
    operations: tuple[Operation, ...]  # including what was added around the block
    result: BlockResult
    residual_before: Region
    residual_after: Region
    program_index: int = 0  # position of the block in the program (a partial plan holds only some blocks)
    cut_off: Region = field(default_factory=Region.empty)  # what this block separated from the held part
    shown_before: Region | None = None  # the material the pictures show before / after the block when the check found that a block cut into the part
    shown_after: Region | None = None  # (`ui/damage.py`); None: as planned. Never used for planning, the files or the export.

    @property
    def material_before(self) -> Region:
        """The material as the pictures show it before the block."""
        return self.residual_before if self.shown_before is None else self.shown_before

    @property
    def material_after(self) -> Region:
        """The material as the pictures show it after the block: with what the check found cut away from the finished part."""
        return self.residual_after if self.shown_after is None else self.shown_after

    @property
    def number(self) -> int:
        """The number the user sees for this block (1-based, as in the flow list)."""
        return self.program_index + 1


@dataclass(frozen=True)
class LeftOutBlock:
    """A selected block that could not be planned: its contour is missing or invalid (C10), or its values do not work out."""

    program_index: int
    name: str
    reason: str

    @property
    def number(self) -> int:
        return self.program_index + 1

    @property
    def text(self) -> str:
        return f"block {self.number}{' ' + self.name if self.name else ''} is left out: {self.reason}"


@dataclass(frozen=True)
class ProgramPlan:
    stock: Region
    blocks: tuple[BlockPlan, ...]
    closing: tuple[Operation, ...]  # retract and switch-off at the end
    left_out: tuple[LeftOutBlock, ...] = ()  # blocks that are not in the plan (C10); the program is incomplete
    workholding_problem: str = ""  # why the chosen workholding is not used (empty: all is well)
    workholding_notes: tuple[str, ...] = ()  # where the placed jaws and the Setup disagree (WH3)

    @property
    def operations(self) -> list[Operation]:
        result: list[Operation] = []
        for plan in self.blocks:
            result.extend(plan.operations)
        result.extend(self.closing)
        return result

    @property
    def messages(self) -> list[str]:
        notes = [message for plan in self.blocks for message in plan.result.messages]
        for left in self.left_out:
            later = [p.number for p in self.blocks if p.program_index > left.program_index]
            tail = f"; the material it should remove is still there for block {', '.join(map(str, later))}" if later else ""
            notes.append(f"{left.text}{tail}")
        if self.workholding_problem:
            notes.append(self.workholding_problem)
        notes.extend(self.workholding_notes)
        return notes

    @property
    def final_residual(self) -> Region:
        return self.blocks[-1].residual_after if self.blocks else self.stock


def _last_point(operations: list[Operation], default: Point | None) -> Point | None:
    for operation in reversed(operations):
        end = getattr(operation, "end", None)
        if isinstance(end, Point):
            return end
    return default


@dataclass
class _MachineState:
    """What the machine is doing between two blocks, as far as the plan knows."""

    position: Point | None = None
    tool_number: int | None = None
    spindle: SpindleSetting | None = None
    coolant: CoolantMode = CoolantMode.NONE


def _retreat(position: Point | None, safety: Safety) -> list[Operation]:
    """Out to the safe radius on the side the tool is on (the far side: below the axis); nothing when it is out already."""
    if position is not None and abs(position.x) < safety.safe_radius_mm:
        return [Rapid(Point(-safety.safe_radius_mm if position.x < 0 else safety.safe_radius_mm, position.z))]
    return []


def _reason_to_skip(program: Program, block: Block) -> str:
    """Why a block cannot be planned before it is tried (its contour, its tool); empty if all is well."""
    problem = program.contour_problem(block)
    if problem:
        return problem
    if block.needs_tool and block.tool_number == NO_TOOL_NUMBER:
        return "no tool chosen"
    return ""


def _generate(
    program: Program, block: Block, residual: Region, jaws: Region | None, cache: PlanCache | None,
) -> tuple[tuple, CachedBlock | None, BlockResult]:
    """The result of one block on the material before it: (the inputs of the plan cache, what the cache knew, the result)."""
    tool = program.equipped_tool(block.tool_number)
    inputs = (block, tool, program.raw_part, program.safety, program.contours, program.workholding)
    known = None if cache is None else cache.get(inputs, residual)
    if known is not None:
        return inputs, known, known.result
    if block.works_on_far_side(tool):  # planned with the tool turned over the axis, the moves turned back (analytic/far_side.py)
        context = BlockContext(program.raw_part, turned_tool(tool), residual, turned_safety(program.safety), program.contours, jaws)
        return inputs, None, turned_result(block.generate(context))
    return inputs, None, block.generate(BlockContext(program.raw_part, tool, residual, program.safety, program.contours, jaws))


def _moves_before(block: Block, state: _MachineState, safety: Safety) -> list[Operation]:
    """What lies between the last block and this one: the retract, the tool change, the spindle and coolant settings."""
    before = _retreat(state.position, safety)
    changes_tool = block.needs_tool and state.tool_number != block.tool_number
    # a tool change happens at its own position
    target = Point(safety.change_point_x, safety.change_point_z) if changes_tool else Point(safety.safe_radius_mm, safety.safe_z_mm)
    if state.position != target:
        before.append(Rapid(target, at_change=changes_tool))
    if block.needs_tool:
        if changes_tool:
            before.append(ToolChange(block.tool_number))
        if state.spindle != block.spindle:
            before.append(SetSpindle(block.spindle))
        if state.coolant != block.coolant:
            before.append(SetCoolant(block.coolant))
    return before


def _block_operations(index: int, result: BlockResult, before: list[Operation]) -> list[Operation]:
    """The operations of the block with what comes before it. The block markers go first so a postprocessor sees the whole block as one unit."""
    body = [replace(op, index=index) if isinstance(op, BlockBegin) else op for op in result.operations]
    begin = [op for op in body if isinstance(op, BlockBegin)]
    rest = [op for op in body if not isinstance(op, BlockBegin)]
    return [*begin, *before, *rest]


def _advance(state: _MachineState, block: Block, operations: list[Operation]) -> None:
    """The state of the machine after the block."""
    state.position = _last_point(operations, state.position)
    if block.needs_tool:
        state.tool_number, state.spindle, state.coolant = block.tool_number, block.spindle, block.coolant
        for operation in operations:  # a block may change the spindle itself (a finishing speed)
            state.spindle = spindle_after(state.spindle, operation)
    if block.stops_spindle:
        state.spindle = None


def _closing(state: _MachineState, safety: Safety) -> list[Operation]:
    """The end of the program: retract, to the tool change position, spindle and coolant off."""
    closing = _retreat(state.position, safety)
    closing.append(Rapid(Point(safety.change_point_x, safety.change_point_z), at_change=True))
    closing.append(StopSpindle())
    if state.coolant is not CoolantMode.NONE:
        closing.append(SetCoolant(CoolantMode.NONE))
    return closing


def plan_program(
    program: Program,
    only_block: int | None = None,
    selection: Collection[int] | None = None,
    unticked_done: bool = True,
    cache: PlanCache | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ProgramPlan:
    """Plan all blocks, or only a selection of them (requirements B9, B15).

    only_block is a selection of one block. The plan holds the moves of the selected
    blocks only; each `BlockPlan` knows its position in the program.
    unticked_done: the blocks that are not selected count as done, so the material they
    remove is gone before the selected blocks that follow them (the default); or they
    count as not done and the material stays. A block after the last selected one is
    not worked out at all.
    Every selected block starts from an unknown machine state, so it gets a safe
    retract, a tool change and its spindle and coolant settings; the blocks before
    the first selected one put no moves into the plan.
    cache: what an earlier plan worked out (`plan_cache.py`): a block with the same inputs and the same material before it is
    taken from there instead of being planned again, and the cache gets what is planned now.
    should_stop: asked before every block; True ends the planning with `PlanningStopped` (what was planned stays in the cache).
    """
    if only_block is not None:
        selection = (only_block,)
    chosen = None if selection is None else frozenset(selection)
    if chosen is not None:
        for index in chosen:
            if not 0 <= index < len(program.blocks):
                raise BlockError(f"there is no block {index + 1}")
    stock = stock_region(program.raw_part) if cache is None else cache.stock(program.raw_part, stock_region)
    safety = program.safety
    residual = stock
    jaws, workholding_problem = program_jaws(program.raw_part, program.workholding) if cache is None else cache.jaws(program.raw_part, program.workholding, program_jaws)
    grip_inside = program.workholding is not None and program.workholding.grip is GripMode.INSIDE
    state = _MachineState()
    plans: list[BlockPlan] = []
    left_out: list[LeftOutBlock] = []

    for index, block in enumerate(program.blocks):
        stop_if_asked(should_stop)
        selected = chosen is None or index in chosen
        if chosen is not None and index > max(chosen, default=-1):
            break  # nothing after the last selected block matters
        if not selected and not unticked_done:
            continue  # not done: its material stays
        reason = _reason_to_skip(program, block)
        if not reason:
            try:  # one block that cannot be planned is left out; the others are still planned
                inputs, known, result = _generate(program, block, residual, jaws, cache)
            except (BlockError, ValueError) as error:  # a bad value, a contour that does not fit, a geometry error
                reason = str(error)
            except ArithmeticError as error:  # GUESS: a calculation that fails on a shape it did not expect (a division by zero) leaves out this block only
                reason = f"a calculation of the planner failed ({type(error).__name__}: {error}); please send the project file"
        if reason:
            if selected:
                left_out.append(LeftOutBlock(index, block.name, reason))
            continue
        if known is None:
            residual_after, cut_off = split_off(residual.difference(result.removed), grip_inside)
            if cache is not None:
                cache.put(inputs, CachedBlock(residual, result, residual_after, cut_off))
        else:
            residual_after, cut_off = known.residual_after, known.cut_off
        if not selected:
            residual = residual_after
            continue

        operations = _block_operations(index, result, _moves_before(block, state, safety))
        if not cut_off.is_empty:
            result = replace(result, messages=result.messages + (
                f"block {index + 1} ({block.title}): a piece is cut off and left out of the following blocks",
            ))
        plans.append(BlockPlan(block, tuple(operations), result, residual, residual_after, index, cut_off))
        residual = residual_after
        _advance(state, block, operations)

    closing = _closing(state, safety) if plans else []
    return ProgramPlan(stock, tuple(plans), tuple(closing), tuple(left_out), workholding_problem,
                       raw_part_notes(program.raw_part, program.workholding) + workholding_notes(program.raw_part, program.workholding))
