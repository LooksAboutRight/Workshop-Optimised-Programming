import tempfile
import unittest
from pathlib import Path

from dataclasses import replace

from wop.core.blocks.base import BlockError
from wop.ui.app_model import AppModel, ModelError, default_contour


class AppModelTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.calls = 0
        self.model.subscribe(self._count)

    def _count(self):
        self.calls += 1

    def test_a_new_project_is_empty_and_clean(self):
        self.assertEqual(self.model.blocks, ())
        self.assertFalse(self.model.dirty)
        self.assertIsNotNone(self.model.analysis.plan)

    def test_blocks_are_added_after_the_selected_one(self):
        self.model.add_block("facing")
        self.model.add_block("turning")
        self.model.select(0)
        self.model.add_block("machine_function")
        self.assertEqual([b.type_name for b in self.model.blocks], ["facing", "machine_function", "turning"])
        self.assertEqual(self.model.selected, 1)
        self.assertEqual(len({b.block_id for b in self.model.blocks}), 3)

    def test_changes_notify_and_mark_the_project_as_changed(self):
        self.model.add_block("facing")
        self.assertTrue(self.model.dirty)
        self.assertGreater(self.calls, 0)
        self.assertTrue(self.model.title().endswith("*"))

    def test_delete_and_move(self):
        for name in ("facing", "turning", "machine_function"):
            self.model.add_block(name)
        self.assertEqual(self.model.move_block(2, -1), 1)
        self.assertEqual([b.type_name for b in self.model.blocks], ["facing", "machine_function", "turning"])
        self.assertEqual(self.model.move_block(0, -1), 0)  # already first: nothing happens
        self.model.delete_block(0)
        self.assertEqual([b.type_name for b in self.model.blocks], ["machine_function", "turning"])
        with self.assertRaises(ModelError):
            self.model.delete_block(5)

    def test_an_invalid_block_is_refused_by_its_own_check(self):
        self.model.add_block("facing")
        with self.assertRaises(BlockError):
            replace(self.model.blocks[0], feed_mm_per_rev=0)

    def test_the_plan_and_picture_follow_the_program(self):
        self.model.add_block("facing")
        self.model.add_block("turning")
        self.assertEqual(len(self.model.analysis.plan.blocks), 2)
        self.assertIn("<svg", self.model.picture())

    def test_the_picture_follows_the_colour_set_and_the_legend_can_be_left_out(self):
        from wop.ui.theme import DARK_COLORS

        self.model.add_block("facing")
        calls = self.calls
        self.model.dirty = False
        self.model.set_colors(DARK_COLORS)
        self.assertEqual(self.calls, calls + 1)  # the window redraws
        self.assertFalse(self.model.dirty)  # a theme is not a change of the project
        self.model.set_colors(DARK_COLORS)
        self.assertEqual(self.calls, calls + 1)  # the same set again: nothing happens
        self.assertIn(DARK_COLORS.block_colors[0], self.model.picture())
        self.assertNotIn("dashed = rapid moves", self.model.picture(with_legend=False))
        self.assertIn("dashed = rapid moves", self.model.picture())

    def test_the_legend_lists_the_blocks_up_to_the_one_asked_for(self):
        self.model.add_block("facing")
        self.model.add_block("turning")
        self.assertEqual(len(self.model.legend().blocks), 2)
        self.assertEqual(len(self.model.legend(0).blocks), 1)

    def test_a_used_contour_cannot_be_removed_directly(self):
        self.model.add_block("turning_contour")
        self.assertEqual(self.model.program.contours, ())  # a new block never gets a contour (C10)
        self.model.set_contour(default_contour(self.model.program))
        self.model.replace_block(0, replace(self.model.blocks[0], contour_id="contour1"))
        with self.assertRaises(ModelError):
            self.model.remove_contour("contour1")
        self.model.delete_block(0)
        self.model.remove_contour("contour1")
        self.assertEqual(self.model.program.contours, ())

    def test_a_single_block_can_be_checked_alone(self):
        self.model.add_block("facing")
        self.model.add_block("turning")
        alone = self.model.single_block_analysis(1)
        self.assertEqual(len(alone.plan.blocks), 1)
        self.assertEqual(len(self.model.analysis.plan.blocks), 2)

    def test_gcode_comes_out_of_the_program(self):
        self.model.add_block("facing")
        result = self.model.gcode()
        self.assertIn("G18", result.text)
        self.assertIn("(Block 1", result.text)

    def test_the_moves_to_the_tool_change_position_are_written_in_machine_coordinates(self):
        from wop.core.lathe.machine import MachineDef

        self.model.add_block("facing")
        self.model.set_machine(MachineDef(name="m", machine_change_radius_mm=50, machine_change_z_mm=-5))
        lines = self.model.gcode().text.splitlines()
        self.assertEqual(sum(line.endswith(" G53 G0 X100 Z-5") for line in lines), 2)  # before the tool change and at the end

    def test_the_shipped_post_numbers_every_line_but_the_comments(self):
        self.model.add_block("facing")
        lines = self.model.gcode().text.splitlines()
        self.assertEqual(lines[3:5], ["N10 G18 G21 G90 G40 G95 G7", "N20 G54"])
        self.assertTrue(lines[2].startswith("("))  # a comment has no number
        self.assertTrue(lines[-1].startswith("N") and lines[-1].endswith(" M30"))
        numbers = [int(line.split()[0][1:]) for line in lines if line.startswith("N")]
        self.assertEqual(numbers, list(range(10, 10 * len(numbers) + 1, 10)))

    def test_accepted_remedies_are_passed_on_and_a_single_block_has_its_own_picture(self):
        from wop.core.program_model.operations import SpindleMode, SpindleSetting

        self.model.add_block("facing")
        block = self.model.blocks[0]
        css = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 150, 3000)
        self.model.replace_block(0, replace(block, spindle=css))
        first = self.model.gcode()
        keys = {i.key for i in first.issues if i.key is not None}
        accepted = self.model.gcode(accepted=keys)
        self.assertEqual(self.model.gcode(accept_all=True).text, accepted.text)
        alone = self.model.single_block_analysis(0)
        self.assertIn("<svg", self.model.picture(analysis=alone))

    def test_save_open_and_the_title(self):
        self.model.add_block("facing")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.wop.json"
            with self.assertRaises(ModelError):
                self.model.save()
            self.model.save(path)
            self.assertFalse(self.model.dirty)
            other = AppModel()
            other.open(path)
            self.assertEqual(other.project, self.model.project)
            self.assertEqual(other.title(), "a.wop.json")
            with self.assertRaises(ModelError):
                other.open(Path(folder) / "missing.wop.json")

    def test_new_starts_over(self):
        self.model.add_block("facing")
        self.model.new()
        self.assertEqual(self.model.blocks, ())
        self.assertFalse(self.model.dirty)


class ToolListTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()

    def test_tools_are_added_with_the_next_number_and_chosen(self):
        number = self.model.add_tool_of_type("turning")
        self.assertEqual(number, 3)
        self.assertEqual(self.model.program.tools[-1].name, "Turning tool")
        self.assertEqual(self.model.selected_tool, 3)
        self.assertTrue(self.model.tools_view)

    def test_a_tool_in_use_cannot_be_removed_but_can_be_edited(self):
        self.model.add_block("facing")
        used = self.model.blocks[0].tool_number
        with self.assertRaises(ModelError):
            self.model.remove_tool(used)
        form = replace(self.model.tool_form(used), name="renamed")
        self.model.edit_tool(used, form)
        self.assertEqual(self.model.program.tool(used).name, "renamed")
        self.assertEqual(self.model.program.tool(used).number, used)

    def test_every_tool_type_can_be_added(self):
        for type_name, _label in self.model.tool_type_choices():
            number = self.model.add_tool_of_type(type_name)
            self.assertEqual(self.model.program.tool(number).kind, type_name)

    def test_editing_a_holder_part_updates_its_codes_in_the_stored_tool(self):
        number = self.model.add_tool_of_type("holder")
        self.model.edit_tool(number, replace(self.model.tool_form(number), hand="L"))
        self.assertEqual(self.model.tool_form(number).holder_code, "PCLNL 2525 M12")
        self.model.edit_tool(number, replace(self.model.tool_form(number), insert_code="DNMG 110408"))
        self.assertEqual(self.model.tool_form(number).holder_code, "PDLNL 2525 M11")

    def test_bad_values_are_refused_and_the_tool_stays(self):
        number = self.model.add_tool_of_type("drill")
        with self.assertRaises(ModelError):
            self.model.edit_tool(number, replace(self.model.tool_form(number), diameter_mm=0))
        self.assertEqual(self.model.program.tool(number).definition["diameter_mm"], 6)

    def test_adding_a_tool_leaves_a_selected_block(self):
        self.model.add_block("facing")
        self.assertIsNotNone(self.model.selected)
        self.model.add_tool_of_type("drill")
        self.assertIsNone(self.model.selected)
        self.assertTrue(self.model.tools_view)

    def test_a_tool_number_can_be_changed_to_a_free_one_and_the_blocks_follow(self):
        self.model.add_block("facing")
        used = self.model.blocks[0].tool_number
        self.model.show_tools(used)
        self.model.edit_tool(used, replace(self.model.tool_form(used), number=9))
        self.assertEqual(self.model.blocks[0].tool_number, 9)
        self.assertEqual(self.model.program.tool(9).definition["number"], 9)
        self.assertEqual(self.model.selected_tool, 9)
        self.assertEqual(self.model.tool_form(9).number, 9)

    def test_a_tool_number_that_is_taken_or_below_one_is_refused(self):
        for bad in (2, 0, -3):
            with self.subTest(number=bad), self.assertRaises(ModelError):
                self.model.edit_tool(1, replace(self.model.tool_form(1), number=bad))
        self.assertEqual([t.number for t in self.model.program.tools], [1, 2])


    def test_a_free_tool_can_be_removed_and_the_choice_moves_on(self):
        number = self.model.add_tool_of_type("turning")
        self.model.remove_tool(number)
        self.assertEqual([t.number for t in self.model.program.tools], [1, 2])
        self.assertEqual(self.model.selected_tool, 1)

    def test_the_tool_material_is_part_of_the_form(self):
        from wop.core.tooling.tool import ToolMaterial

        number = self.model.add_tool_of_type("turning")
        self.model.edit_tool(number, replace(self.model.tool_form(number), material=ToolMaterial.CERAMIC))
        self.assertEqual(self.model.program.tool(number).material, ToolMaterial.CERAMIC)

    def test_choosing_a_block_leaves_the_tools_view(self):
        self.model.add_block("facing")
        self.model.show_tools()
        self.model.select(0)
        self.assertFalse(self.model.tools_view)

    def test_contour_ids_are_unique(self):
        self.model.set_contour(default_contour(self.model.program))
        self.assertEqual(self.model.next_contour_id(), "contour2")


if __name__ == "__main__":
    unittest.main()
