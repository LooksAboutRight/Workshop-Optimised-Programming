"""Step through the planned program move by move (requirement V2), without any GUI toolkit.

A `Stepper` lists every move of a plan (rapid, line, arc) as a `StepFrame`. For a frame it
gives the material left at that moment, the tool and where its tip is. The material is
worked out when a frame is asked for, from the start of its block: each cutting move removes
what the tool body passes (as `verify_plan` does: a straight move as the area it sweeps, an arc in steps). The last move of a block shows exactly
the material the plan has after the block.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from ..core.analytic import mirror
from ..core.analytic.far_side import turned_point, turned_tool
from ..core.geometry import Point
from ..core.program_model.operations import (
    ArcMove, LinearMove, Rapid, SpindleSetting, ToolChange, plain_moves, spindle_after, spindle_text,
)
from ..core.program_model.program import Program, ProgramPlan
from ..core.reach import PreparedTool, prepare_tool
from ..core.geometry.region import Region
from ..core.verify import move_points
from .ui_constants import MAX_PRECOMPUTED_STEPS


@dataclass(frozen=True)
class StepFrame:
    block_index: int  # position in plan.blocks
    block_number: int  # number shown to the user
    move_number: int  # 1-based among the moves of the block
    moves_in_block: int
    tool_number: int
    start: Point | None  # None for the very first move of the program
    move: Rapid | LinearMove | ArcMove
    index: int  # position in the stepper's list
    operation_index: int = 0  # the operation of the block this move comes from (as in `Finding`)
    spindle: SpindleSetting | None = None  # the spindle while this move runs; None = stopped (WH0)

    @property
    def spindle_on(self) -> bool:
        return self.spindle is not None

    @property
    def is_cutting(self) -> bool:
        return not isinstance(self.move, Rapid)

    @property
    def end(self) -> Point:
        return self.move.end

    @property
    def text(self) -> str:
        kind = "rapid" if isinstance(self.move, Rapid) else "arc" if isinstance(self.move, ArcMove) else "cut"
        return (
            f"Block {self.block_number}, move {self.move_number} of {self.moves_in_block}: "
            f"T{self.tool_number} {kind} to X {self.end.x:.3f}, Z {self.end.z:.3f}. "
            f"Spindle: {spindle_text(self.spindle)}"
        )


def spindle_after_block(plan: ProgramPlan, block_index: int | None) -> SpindleSetting | None:
    """The spindle (None = stopped) after block `block_index` of the plan (None: after the last block), WH0/WH4."""
    last = len(plan.blocks) - 1 if block_index is None else block_index
    spindle: SpindleSetting | None = None
    for block_plan in plan.blocks[: last + 1]:
        for original in block_plan.operations:
            for operation in plain_moves(original):
                spindle = spindle_after(spindle, operation)
    return spindle


class Stepper:
    def __init__(self, program: Program, plan: ProgramPlan) -> None:
        self.program = program
        self.plan = plan
        self.frames: list[StepFrame] = []
        self._first: dict[int, int] = {}
        self._build()
        self._materials: dict[int, Region] = {}
        self._prepared: dict[tuple[int, bool], PreparedTool] = {}
        self._lock = threading.RLock()  # the background work and the window ask for materials; one at a time
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    def _build(self) -> None:
        position: Point | None = None
        tool = None
        spindle: SpindleSetting | None = None  # a program starts with the spindle stopped
        for block_index, block_plan in enumerate(self.plan.blocks):
            if tool is None:
                tool = block_plan.block.tool_number
            moves = []
            for operation_index, original in enumerate(block_plan.operations):
                for move in plain_moves(original):
                    if isinstance(move, ToolChange):
                        tool = move.tool_number
                    elif isinstance(move, (Rapid, LinearMove, ArcMove)):
                        moves.append((tool, move, operation_index, spindle))
                    else:
                        spindle = spindle_after(spindle, move)
            if moves:
                self._first[block_index] = len(self.frames)
            for number, (move_tool, move, operation_index, move_spindle) in enumerate(moves, 1):
                self.frames.append(
                    StepFrame(
                        block_index, block_plan.number, number, len(moves), move_tool, position, move,
                        len(self.frames), operation_index, move_spindle,
                    )
                )
                position = move.end

    # --- navigation ---------------------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self.frames)

    def frame(self, index: int) -> StepFrame:
        if not 0 <= index < len(self.frames):
            raise IndexError("there is no such step")
        return self.frames[index]

    def block_start(self, index: int) -> int:
        """The first step of the block that step `index` belongs to."""
        return self._first[self.frame(index).block_index]

    def block_end(self, index: int) -> int:
        """The last step of the block that step `index` belongs to."""
        frame = self.frame(index)
        return self.block_start(index) + frame.moves_in_block - 1

    def first_step_of_block(self, block_index: int) -> int | None:
        """The first step of a block (None if it has no moves)."""
        return self._first.get(block_index)

    def collisions(self, index: int, findings) -> list:
        """The findings (verify_plan) that belong to the move of this step."""
        frame = self.frame(index)
        return [
            f for f in findings
            if f.block_index == frame.block_index and f.operation_index == frame.operation_index
        ]

    # --- what a step shows ----------------------------------------------------------------

    def prepared_tool(self, tool_number: int, turned: bool = False) -> PreparedTool:
        """The tool as it stands; `turned`: over the axis (the tool of a block on the far side, used to work out the material: the part is
        round and its material is kept as the half above the axis)."""
        if (tool_number, turned) not in self._prepared:
            tool = self.program.equipped_tool(tool_number)
            self._prepared[(tool_number, turned)] = prepare_tool(turned_tool(tool) if turned else tool)
        return self._prepared[(tool_number, turned)]

    def tool_body(self, index: int) -> Region:
        """The cutter (and holder body) placed with its tip at the end of the step."""
        frame = self.frame(index)
        return self.prepared_tool(frame.tool_number).body.translated(frame.end.x, frame.end.z)

    def holder_outlines(self, index: int) -> list[list[Point]]:
        frame = self.frame(index)
        tip = frame.end
        prepared = self.prepared_tool(frame.tool_number)
        return [[Point(p.x + tip.x, p.z + tip.z) for p in outline] for outline in prepared.holder_outlines]

    def precompute(self, start: int) -> None:
        """Work out the materials of the steps in a background thread, from step `start` to the end of the program (at most
        `MAX_PRECOMPUTED_STEPS`), then the steps before it. Whoever needs a step before it is done works it out itself.
        A new call stops the one before."""
        self.stop_precompute()
        start = max(0, min(start, max(self.count - 1, 0)))
        order = [*range(start, self.count), *range(start)][:MAX_PRECOMPUTED_STEPS]
        stop = self._stop = threading.Event()
        self._worker = threading.Thread(target=self._precompute, args=(order, stop), daemon=True)
        self._worker.start()

    def stop_precompute(self) -> None:
        """Stop the background work (the steps already done stay)."""
        self._stop.set()

    def wait_precompute(self, timeout: float | None = None) -> bool:
        """Wait for the background work to end (for tests); False when it is still running after `timeout` seconds."""
        worker = self._worker
        if worker is not None:
            worker.join(timeout)
            return not worker.is_alive()
        return True

    def _precompute(self, order: list[int], stop: threading.Event) -> None:
        for index in order:
            if stop.is_set():
                return
            try:
                self.material(index)
            except Exception:  # noqa: BLE001  (the window meets the same error when it asks for this step)
                return

    def material(self, index: int) -> Region:
        """The material left when the step is done."""
        with self._lock:
            return self._material(index)

    def _material(self, index: int) -> Region:
        if index in self._materials:
            return self._materials[index]
        frame = self.frame(index)
        block_plan = self.plan.blocks[frame.block_index]
        start = self.block_start(index)
        if index == self.block_end(index):
            self._materials[index] = block_plan.material_after
            return block_plan.material_after
        current = self._materials.get(index - 1) if index > start else block_plan.material_before
        if current is None:  # compute the steps in between, from the nearest known one
            known = max((i for i in self._materials if start <= i < index), default=start - 1)
            current = self._materials[known] if known >= start else block_plan.material_before
            for i in range(known + 1, index):
                current = self._after_move(current, self.frames[i])
                self._materials[i] = current
        result = self._after_move(current, frame)
        self._materials[index] = result
        return result

    def swept(self, block_index: int, start: Region) -> Region:
        """The material after every cutting move of the block, swept one after the other from `start`: what the machine really leaves (a
        cut into the finished part is in it), where the plan keeps the planned material."""
        current = start
        for frame in self.frames:
            if frame.block_index == block_index:
                current = self._after_move(current, frame)
        return current

    def _after_move(self, current: Region, frame: StepFrame) -> Region:
        if not frame.is_cutting:
            return current
        far = self.plan.blocks[frame.block_index].block.works_on_far_side(self.program.equipped_tool(frame.tool_number))
        body = self.prepared_tool(frame.tool_number, far).body
        frame_start, move = (turned_point(frame.start), mirror.MIRROR_X.operation(frame.move)) if far else (frame.start, frame.move)
        if frame_start is not None and isinstance(move, LinearMove):  # a straight move: the whole area it sweeps at once (as `verify_plan`)
            start, end = frame_start, move.end
            return current.difference(body.swept(end.x - start.x, end.z - start.z).translated(start.x, start.z))
        for point in move_points(frame_start, move):  # an arc: the tool body at every step along it
            current = current.difference(body.translated(point.x, point.z))
        return current
