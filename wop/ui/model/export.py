"""Export: the ticks of the blocks, the check before the export and the G-code."""

from __future__ import annotations

from datetime import datetime

from ...core.program_model.units import UnitSystem
from ...post.base import PostSettings
from ...post.context import make_context
from ...post.engine import TemplatePost
from ...post.generate import generate_gcode, GenerationResult
from .helpers import Analysis, ExportReport


class ExportMixin:
    """Export: the ticks of the blocks, the check before the export and the G-code. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    def is_ticked(self, index: int) -> bool:
        self._check_index(index)
        return self.blocks[index].block_id not in self._unticked

    def set_ticked(self, index: int, ticked: bool) -> None:
        self._check_index(index)
        block_id = self.blocks[index].block_id
        if ticked:
            self._unticked.discard(block_id)
        else:
            self._unticked.add(block_id)
        self._notify()

    def set_all_ticked(self, ticked: bool) -> None:
        self._unticked = set() if ticked else {block.block_id for block in self.blocks}
        self._notify()

    def ticked_indices(self) -> tuple[int, ...]:
        return tuple(i for i, block in enumerate(self.blocks) if block.block_id not in self._unticked)

    def tick_state(self) -> str:
        """"all", "none" or "some": for the header checkbox of the flow list."""
        ticked = len(self.ticked_indices())
        return "all" if ticked == len(self.blocks) else "none" if ticked == 0 else "some"

    def selection_analysis(self, selection: tuple[int, ...], unticked_done: bool = True, run_check: bool = False) -> Analysis:
        """Plan and check some blocks on their own (B9, B15). The shown analysis stays as it is. The collision and power
        checks run when the automatic check is on or `run_check` is set."""
        for index in selection:
            self._check_index(index)
        return self._analyse(selection, unticked_done, check=True if run_check else None)

    def export_report(
        self, selection: tuple[int, ...] | None = None, unticked_done: bool = True, run_check: bool = False,
    ) -> ExportReport:
        """What is known about the program (or the selected blocks) before the G-code leaves: whether the collision and
        power checks have been run, what they found, and which blocks are left out (that needs no check). The checks
        run only with `run_check` or when the automatic check is on. The program is
        written as drawn: the user decides whether to export in spite of these."""
        if selection is not None:
            analysis = self.selection_analysis(selection, unticked_done, run_check)
        else:
            analysis = self.analysis_now(check=run_check)
        problems = [f"{finding.message} (remedy: {finding.remedy})" for finding in analysis.findings] if analysis.checked else []
        if analysis.plan is not None:
            problems += [left.text for left in analysis.plan.left_out]
        return ExportReport(analysis.checked, tuple(dict.fromkeys(problems)))  # the same text twice (two moves at the same place) once

    def export_problems(self, selection: tuple[int, ...] | None = None, unticked_done: bool = True) -> list[str]:
        """The problems of `export_report` after running the checks (empty: nothing to ask)."""
        return list(self.export_report(selection, unticked_done, run_check=True).problems)

    def single_block_analysis(self, index: int) -> Analysis:
        """Plan and check one block on its own (B9)."""
        return self.selection_analysis((index,))

    def partial_note(self, selection: tuple[int, ...], unticked_done: bool) -> str:
        """The header comment of a partial output: which blocks, and what is assumed about the others."""
        numbers = ", ".join(str(i + 1) for i in selection)
        others = (
            "the other blocks count as done (their material is removed)"
            if unticked_done
            else "the other blocks count as not done (their material is still there)"
        )
        return f"PARTIAL OUTPUT: only block {numbers}; {others}"

    def gcode(
        self,
        only_block: int | None = None,
        accepted: set | None = None,
        accept_all: bool = False,
        selection: tuple[int, ...] | None = None,
        unticked_done: bool = True,
    ) -> GenerationResult:
        """G-code of the program, of one block or of a selection of blocks.

        `accepted` holds the remedies the user accepted. A partial output gets a header comment
        that names the blocks and the assumption about the others.
        """
        if only_block is not None:
            selection = (only_block,)
        plan = self._plan(selection, unticked_done)
        definition, not_found = self.post_library.choose(self.postprocessor_id)
        post = TemplatePost(definition)
        machine = self.project.machine
        title = self.project.settings.title
        settings = PostSettings(self.project.settings.x_mode, machine.unit_system if machine else UnitSystem.METRIC)
        context = make_context(self.program, plan, title, machine.name if machine else "", datetime.now(),
                               machine=machine, work_offset=self.project.settings.work_offset)
        notes = (not_found,) if not_found else ()
        notes += () if selection is None else (self.partial_note(tuple(sorted(selection)), unticked_done),)
        chosen = set(accepted or ())
        if accept_all:
            first = generate_gcode(plan, post, settings, header_notes=notes, context=context)
            chosen |= {issue.key for issue in first.issues if issue.key is not None}
        return generate_gcode(plan, post, settings, chosen, notes, context)
