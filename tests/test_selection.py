import unittest
from dataclasses import replace

from tests.reference_program import reference_program
from wop.core.blocks.base import BlockError
from wop.core.program_model.project import Project
from wop.core.program_model.program import plan_program
from wop.ui.app_model import AppModel
from wop.ui.svg_preview import legend_for, render_svg
from wop.ui.theme import LIGHT_COLORS


class SelectionPlanTests(unittest.TestCase):
    """Requirement B15: some blocks on their own."""

    def setUp(self):
        self.program = reference_program()
        self.full = plan_program(self.program)

    def test_only_the_selected_blocks_are_in_the_plan_and_know_their_number(self):
        plan = plan_program(self.program, selection=(1, 3))
        self.assertEqual([p.program_index for p in plan.blocks], [1, 3])
        self.assertEqual([p.number for p in plan.blocks], [2, 4])

    def test_unticked_blocks_count_as_done_by_default(self):
        plan = plan_program(self.program, selection=(1, 3))
        self.assertAlmostEqual(plan.blocks[1].residual_before.area, self.full.blocks[3].residual_before.area)

    def test_unticked_blocks_can_count_as_not_done(self):
        done = plan_program(self.program, selection=(3,))
        not_done = plan_program(self.program, selection=(3,), unticked_done=False)
        self.assertAlmostEqual(not_done.blocks[0].residual_before.area, not_done.stock.area)
        self.assertGreater(not_done.blocks[0].residual_before.area, done.blocks[0].residual_before.area)

    def test_with_not_done_a_selected_block_still_sees_the_selected_blocks_before_it(self):
        plan = plan_program(self.program, selection=(1, 2), unticked_done=False)
        self.assertAlmostEqual(plan.blocks[1].residual_before.area, plan.blocks[0].residual_after.area)

    def test_an_empty_selection_gives_an_empty_plan(self):
        plan = plan_program(self.program, selection=())
        self.assertEqual(plan.blocks, ())
        self.assertEqual(plan.closing, ())

    def test_blocks_after_the_last_selected_one_are_not_worked_out(self):
        broken = replace(self.program.blocks[0], block_id="x", tool_number=99)  # a tool that does not exist
        program = replace(self.program, blocks=self.program.blocks + (broken,))
        self.assertEqual(len(plan_program(program, selection=(0,)).blocks), 1)
        self.assertEqual(plan_program(program, selection=(0,)).left_out, ())  # not looked at: no reason to leave it out
        self.assertEqual(len(plan_program(program).left_out), 1)  # looked at: left out, with its reason

    def test_a_block_that_does_not_exist_is_refused(self):
        for selection in ((9,), (-1,), (0, 9)):
            with self.assertRaises(BlockError):
                plan_program(self.program, selection=selection)

    def test_one_block_is_the_old_single_block_plan(self):
        a = plan_program(self.program, only_block=2)
        b = plan_program(self.program, selection=(2,))
        self.assertEqual(a.operations, b.operations)

    def test_the_picture_legend_and_colours_use_the_numbers_of_the_program(self):
        plan = plan_program(self.program, selection=(1, 3))
        rows = legend_for(plan).blocks
        self.assertTrue(rows[0][1].startswith("2:"))
        self.assertTrue(rows[1][1].startswith("4:"))
        self.assertEqual(rows[0][0], LIGHT_COLORS.block_colors[1])
        self.assertEqual(rows[1][0], LIGHT_COLORS.block_colors[3])
        self.assertIn(">4</text>", render_svg(plan))


class TickingTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.model.project = Project(reference_program())
        self.model.refresh()
        self.count = len(self.model.blocks)

    def test_all_blocks_are_ticked_at_first(self):
        self.assertEqual(self.model.ticked_indices(), tuple(range(self.count)))
        self.assertEqual(self.model.tick_state(), "all")

    def test_a_tick_can_be_removed_and_the_state_follows(self):
        self.model.set_ticked(1, False)
        self.assertFalse(self.model.is_ticked(1))
        self.assertNotIn(1, self.model.ticked_indices())
        self.assertEqual(self.model.tick_state(), "some")
        self.model.set_all_ticked(False)
        self.assertEqual((self.model.ticked_indices(), self.model.tick_state()), ((), "none"))
        self.model.set_all_ticked(True)
        self.assertEqual(self.model.tick_state(), "all")

    def test_ticking_is_not_a_change_of_the_project_and_notifies_the_window(self):
        calls = []
        self.model.subscribe(lambda: calls.append(1))
        self.model.set_ticked(0, False)
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.model.dirty)

    def test_the_tick_belongs_to_the_block_when_blocks_move(self):
        self.model.set_ticked(0, False)
        self.model.move_block(0, 1)
        self.assertFalse(self.model.is_ticked(1))
        self.assertTrue(self.model.is_ticked(0))

    def test_a_deleted_block_does_not_hand_its_tick_to_a_new_block(self):
        self.model.set_ticked(self.count - 1, False)
        self.model.delete_block(self.count - 1)
        self.model.add_block("facing")
        self.assertTrue(all(self.model.is_ticked(i) for i in range(len(self.model.blocks))))

    def test_a_new_project_has_everything_ticked(self):
        self.model.set_all_ticked(False)
        self.model.new()
        self.assertEqual(self.model.tick_state(), "all")

    def test_a_partial_output_names_the_blocks_and_the_assumption(self):
        done = self.model.gcode(selection=(1, 3), unticked_done=True).text
        not_done = self.model.gcode(selection=(1, 3), unticked_done=False).text
        self.assertIn("PARTIAL OUTPUT: only block 2, 4; the other blocks count as done", done)
        self.assertIn("count as not done", not_done)
        self.assertIn("Block 2:", done)
        self.assertIn("Block 4:", done)
        self.assertNotIn("Block 1:", done)

    def test_the_whole_program_has_no_partial_note(self):
        self.assertNotIn("PARTIAL", self.model.gcode().text)

    def test_one_block_alone_is_a_selection_of_one(self):
        text = self.model.gcode(only_block=2).text
        self.assertIn("PARTIAL OUTPUT: only block 3", text)

    def test_the_analysis_of_a_selection_is_separate_from_the_shown_one(self):
        before = self.model.analysis
        partial = self.model.selection_analysis((2,), unticked_done=False)
        self.assertEqual(len(partial.plan.blocks), 1)
        self.assertIs(self.model.analysis, before)
