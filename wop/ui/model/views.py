"""The plan, the checks and the pictures."""

from __future__ import annotations

import traceback
from dataclasses import replace

from ...core.blocks.base import BlockContext, BlockError
from ...core.geometry import Point, Segment, segments_to_polyline
from ...core.lathe.machine_check import check_against_machine
from ...core.lathe.power import estimate_power
from ...core.program_model.program import plan_program, PlanningStopped, ProgramPlan
from ...core.reach import prepare_tool
from ...core.verify import verify_plan
from ...core.lathe.workholding import place_workholding, WorkholdingError
from ..app_constants import PLAN_CACHE_SIZE, WORKING_CHECKING, WORKING_PLANNING
from ..damage import with_damage
from ..stepper import spindle_after_block, Stepper
from ..svg_preview import Legend, legend_for, render_svg, StepView
from ..theme import ColorSet
from ..view3d import Scene, build_scene
from .helpers import Analysis


class ViewsMixin:
    """The plan, the checks and the pictures. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    def _plan(self, selection: tuple[int, ...] | None, unticked_done: bool, program=None, should_stop=None) -> ProgramPlan:
        """The plan of the program (or of the selected blocks), worked out once for the same program: the analysis, the
        export and the G-code share it. A program is never changed in place, so the same object means the same plan.
        `program`: another than the current one (the background job plans the program it was asked for)."""
        program = self.program if program is None else program
        key = (None if selection is None else tuple(sorted(selection)), unticked_done)
        with self._work_lock:
            if self._plan_cache is None or self._plan_cache[0] is not program:
                self._plan_cache = (program, {})
            plans = self._plan_cache[1]
            if key not in plans:
                if len(plans) >= PLAN_CACHE_SIZE:
                    plans.clear()
                plans[key] = plan_program(
                    program, selection=selection, unticked_done=unticked_done, cache=self._block_cache, should_stop=should_stop,
                )
            return plans[key]

    def _analyse(
        self, selection: tuple[int, ...] | None = None, unticked_done: bool = True, check: bool | None = None, program=None,
        should_stop=None,
    ) -> Analysis:
        """Plan the program and look at it. `check` None: the collision and power checks run when the automatic check is on."""
        check = self.auto_check if check is None else check
        planned = self._planned(selection, unticked_done, program, should_stop)
        return self._checked(planned, should_stop) if check and planned.plan is not None else planned

    def _planned(self, selection, unticked_done: bool, program=None, should_stop=None) -> Analysis:
        """The plan and its notes, not checked yet."""
        program = self.program if program is None else program
        try:
            plan = self._plan(selection, unticked_done, program, should_stop)
            messages = list(plan.messages)
            if self.machine is not None:
                messages += check_against_machine(program, plan, self.machine)
            return Analysis(plan, [], messages, checked=False, program=program)
        except (BlockError, ValueError) as error:
            return Analysis(error=str(error), program=program)

    def _checked(self, planned: Analysis, should_stop=None) -> Analysis:
        """The planned analysis with the collision and power checks."""
        program = planned.program
        try:
            with self._work_lock:
                messages, power = list(planned.messages), None
                if self.machine is not None:
                    material = self.materials.find(program.raw_part.material)
                    power = estimate_power(program, planned.plan, self.machine, material)
                    messages += power.messages
                findings = verify_plan(program, planned.plan, cache=self._block_cache, should_stop=should_stop)
            return replace(planned, plan=with_damage(program, planned.plan, findings), findings=findings, messages=messages, power=power, checked=True)
        except (BlockError, ValueError) as error:
            return Analysis(error=str(error), program=program)

    def run_in_background(self, runner) -> None:
        """The window plans and checks in the background from now on: `runner(job, done)` runs `job()` in another thread and
        calls `done(result)` in the window's thread. Without a runner (tests, tools) `refresh` works at once."""
        self._runner = runner

    def refresh(self) -> Analysis:
        """Plan (and check) the program again. Without a runner at once. With one the shown analysis stays, marked as being
        worked out (`working`), until the plan of the new program is there; then the findings follow. A newer change stops
        the older work between two blocks and its result is not used."""
        check = self.auto_check or self._force_check
        if self._runner is None:
            self.analysis = self._analyse(check=check)
            return self.analysis
        self._generation += 1
        generation, program = self._generation, self.program

        def stale() -> bool:
            return self._generation != generation

        def planned(result: Analysis | None) -> None:
            if result is None or stale():
                return
            follows = check and result.plan is not None
            self.analysis = replace(result, working=WORKING_CHECKING if follows else "")
            self._notify_results()
            if follows:
                self._runner(lambda: self._stoppable(lambda: self._checked(result, stale)), checked)

        def checked(result: Analysis | None) -> None:
            if result is not None and not stale():
                self.analysis = result
                self._notify_results()

        self.analysis = replace(self.analysis, working=WORKING_PLANNING)
        self._runner(lambda: self._stoppable(lambda: self._planned(None, True, program, stale)), planned)
        return self.analysis

    @staticmethod
    def _stoppable(job):
        """The result of a background job; None when it was stopped for a newer program, or failed (the error goes to the log)."""
        try:
            return job()
        except PlanningStopped:
            return None
        except Exception:  # noqa: BLE001  (a background job must not die silently: the error log keeps the traceback)
            traceback.print_exc()
            return None

    def analysis_now(self, check: bool = False) -> Analysis:
        """The analysis of the program as it is now: the shown one when it belongs to this program, is finished and (with `check`)
        checked; else worked out at once (an export must never use the plan of an older program)."""
        shown = self.analysis
        if shown.program is self.program and not shown.working and (shown.checked or not check):
            return shown
        self._generation += 1  # what runs in the background is not needed any more
        self.analysis = self._analyse(check=True if check else None)
        self._notify()
        return self.analysis

    def verify_now(self) -> Analysis:
        """Run the collision and power checks on the whole program now, also when `auto_check` is off."""
        self._force_check = True
        try:
            self._changed(dirty=False)
        finally:
            self._force_check = False
        return self.analysis

    def set_colors(self, colors: ColorSet) -> None:
        """Use another colour set for the pictures (the window follows the OS theme). Not a change of the project."""
        if colors == self.colors:
            return
        self.colors = colors
        for listener in list(self._listeners):
            listener()

    def stepper(self) -> Stepper | None:
        """The steps of the shown plan (V2); None when the program could not be planned. Rebuilt when the plan changes."""
        plan = self.analysis.plan
        if plan is None:
            return None
        if self._stepper is None or self._stepper.plan is not plan:
            self._stepper = Stepper(self.program, plan)
        return self._stepper

    def step_view(self, step: int) -> tuple[int, StepView] | None:
        """(block index, what to draw) for step number `step`; None if there is no such step."""
        stepper = self.stepper()
        if stepper is None or not 0 <= step < stepper.count:
            return None
        frame = stepper.frame(step)
        view = StepView(
            stepper.material(step),
            stepper.tool_body(step),
            tuple(tuple(outline) for outline in stepper.holder_outlines(step)),
            frame.move_number,
        )
        return frame.block_index, view

    def picture(
        self, upto_block: int | None = None, analysis: Analysis | None = None, with_legend: bool = True,
        step: int | None = None, line_scale: float = 1.0,
    ) -> str:
        """SVG text of the program (or of an analysis given), up to upto_block.

        The window asks for no legend and draws its own overlay (`legend`), and gives 1 / its zoom as `line_scale`.
        The picture shows the raw part and the cutting moves; the safe and tool change positions are not in it.
        """
        analysis = analysis or self.analysis
        if analysis.plan is None:
            preview = self._preview_plan(analysis)
            return "" if preview is None else render_svg(preview, None, [], self.colors, with_legend, line_scale=line_scale)
        shown = self.step_view(step) if step is not None and analysis is self.analysis else None
        if shown:
            upto_block = shown[0]
        placed = self._placed_workholding()
        extra: tuple[Point, ...] = ()
        if placed is not None:  # the jaws are always inside the picture (the chuck body is cut off at its edge)
            extra += tuple(point for point in segments_to_polyline(list(placed.jaws)))
        extra += self._far_side_points(analysis.plan)
        outline = self.selected_outline(analysis, upto_block)
        extra += tuple(segments_to_polyline(list(outline))) if outline else ()
        return render_svg(analysis.plan, upto_block, analysis.findings, self.colors, with_legend,
                          shown[1] if shown else None, extra_points=extra, workholding=placed, outline=outline,
                          line_scale=line_scale)

    def selected_outline(self, analysis: Analysis, upto_block: int | None = None) -> tuple[Segment, ...]:
        """The finished shape of the block chosen in the flow list, made from its form values (nothing for a block that
        is not planned, or not shown in the picture). Only this one block, so the picture stays clear."""
        if self.selected is None or analysis.plan is None:
            return ()
        if upto_block is not None and self.selected > upto_block:
            return ()
        block_plan = next((b for b in analysis.plan.blocks if b.program_index == self.selected), None)
        if block_plan is None or not block_plan.block.needs_tool:
            return ()
        try:
            context = BlockContext(
                self.program.raw_part, self.program.equipped_tool(block_plan.block.tool_number),
                block_plan.residual_before, self.program.safety, self.program.contours,
            )
            return block_plan.block.target_outline(context)
        except (BlockError, ValueError):
            return ()

    def _far_side_points(self, plan: ProgramPlan) -> tuple[Point, ...]:
        """Points below the axis that the picture must show: the lowest X a tool body reaches past the axis (a boring
        bar in a small bore), so the far side of the part is in the picture and the scale does not change step by step."""
        lowest: float | None = None
        for block_plan in plan.blocks:
            prepared = prepare_tool(self.program.equipped_tool(block_plan.block.tool_number))
            if prepared.mirror is None:
                continue
            ends = [getattr(op, "end", None) for op in block_plan.operations]
            reach = min((end.x for end in ends if isinstance(end, Point)), default=0) + prepared.body_min_x
            lowest = reach if lowest is None else min(lowest, reach)
        return () if lowest is None or lowest >= 0 else (Point(lowest, self.program.safety.safe_z_mm),)

    def _placed_workholding(self):
        """The jaws and chuck on the machine for the pictures; None if there are none or they cannot be placed."""
        try:
            placed = place_workholding(self.program.raw_part, self.program.workholding)
        except WorkholdingError:
            return None  # the plan's messages say why
        return None if placed.is_empty else placed

    def legend(self, upto_block: int | None = None) -> Legend:
        """The legend of the picture up to upto_block (empty when the program could not be planned)."""
        plan = self.analysis.plan
        if plan is None:
            return Legend()
        return legend_for(plan, upto_block, self.colors)

    @staticmethod
    def _preview_plan(analysis: Analysis) -> ProgramPlan | None:
        """A plan with no blocks whose material is the part saved in the file (V9): what the picture shows until the plan is there."""
        return None if analysis.preview is None else ProgramPlan(analysis.preview, (), ())

    def scene3d(self, upto_block: int | None = None, steps_per_turn: int | None = None, step: int | None = None) -> Scene | None:
        """The 3D scene of the part after upto_block (None: the whole program); None when the program has no plan."""
        plan = self.analysis.plan
        if plan is None:
            preview = self._preview_plan(self.analysis)
            return None if preview is None else build_scene(preview, colors=self.colors, **({} if steps_per_turn is None else {"steps_per_turn": steps_per_turn}))
        shown = self.step_view(step) if step is not None else None
        if shown:
            upto_block = shown[0]
        extra = {"step": shown[1]} if shown else {}
        extra["workholding"] = self._placed_workholding()
        extra["outline"] = self.selected_outline(self.analysis, upto_block)
        if step is not None and shown:  # the jaws turn into a revolve when the spindle runs in this step (WH4)
            extra["spindle_on"] = self.stepper().frame(step).spindle_on
        else:
            extra["spindle_on"] = spindle_after_block(plan, upto_block) is not None
        if steps_per_turn is None:
            return build_scene(plan, upto_block, colors=self.colors, **extra)
        return build_scene(plan, upto_block, steps_per_turn=steps_per_turn, colors=self.colors, **extra)
