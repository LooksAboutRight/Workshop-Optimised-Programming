"""Toolboxes and a project (T18, T19): a project without tools, a block with no tool chosen, the default toolbox of a new
project and the change of the toolbox of a project."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from wop.core.constants import NO_TOOL_NUMBER
from wop.core.files.project_io import program_problems, project_from_json, project_to_json
from wop.core.program_model.program import plan_program
from wop.core.tooling.toolbox import Toolbox, ToolboxEntry
from wop.ui.app_model import AppModel
from wop.ui.model import helpers

ENTRY = ToolboxEntry


class RealProjectCase(unittest.TestCase):
    """The tests normally start with the two stub tools; here a new project is the real one."""

    def setUp(self):
        self.was = helpers.NEW_PROJECT_USES_STUB_TOOLS
        helpers.NEW_PROJECT_USES_STUB_TOOLS = False
        self.addCleanup(setattr, helpers, "NEW_PROJECT_USES_STUB_TOOLS", self.was)
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.settings_path = Path(self._folder.name) / "settings.json"
        self.model = AppModel(settings_path=self.settings_path)
        self.names = [t.name for t in self.model.tool_library]  # the Example library: one tool of each type

    def box(self, name="Standard", *numbers):
        entries = tuple(ENTRY(self.names[i], n) for i, n in numbers) if numbers else (ENTRY(self.names[0], 1), ENTRY(self.names[1], 2, 7))
        return Toolbox(name, entries)


class RealNewProjectTests(RealProjectCase):
    def test_a_new_project_has_no_tools_and_a_block_has_no_tool_chosen(self):
        self.assertEqual(self.model.program.tools, ())
        self.model.add_block("facing")
        self.assertEqual(self.model.blocks[0].tool_number, NO_TOOL_NUMBER)
        plan = plan_program(self.model.program)
        self.assertEqual(plan.blocks, ())
        self.assertEqual([(left.program_index, left.reason) for left in plan.left_out], [(0, "no tool chosen")])
        self.assertEqual(program_problems(self.model.program), [])

    def test_a_machine_function_needs_no_tool(self):
        self.model.add_block("machine_function")
        plan = plan_program(self.model.program)
        self.assertEqual((len(plan.blocks), plan.left_out), (1, ()))

    def test_a_new_block_takes_the_tool_of_the_block_before_else_the_lowest_number(self):
        self.model.save_toolbox(self.box("Standard", (0, 5), (1, 3)))
        self.model.apply_toolbox("Standard")
        self.model.add_block("facing")
        self.assertEqual(self.model.blocks[0].tool_number, 3)
        self.model.replace_block(0, replace(self.model.blocks[0], tool_number=5))
        self.model.add_block("turning")
        self.assertEqual(self.model.blocks[1].tool_number, 5)

    def test_the_default_toolbox_fills_a_new_project(self):
        self.model.save_toolbox(self.box())
        self.model.new()
        self.assertEqual(self.model.program.tools, ())  # no default yet
        self.model.set_default_toolbox("Standard")
        self.model.new()
        tools = self.model.program.tools
        self.assertEqual([(t.number, t.name, t.offset_number) for t in tools], [(1, self.names[0], None), (2, self.names[1], 7)])
        library = self.model.active_library_name("tools")
        self.assertEqual([(t.origin_library, t.origin_name) for t in tools], [(library, self.names[0]), (library, self.names[1])])
        self.assertFalse(self.model.dirty)

    def test_the_project_knows_its_toolbox_and_says_when_the_tools_were_changed(self):
        self.assertEqual(self.model.toolbox_line(), "Toolbox: none")
        self.model.save_toolbox(self.box())
        self.model.apply_toolbox("Standard")
        self.assertEqual(self.model.toolbox_line(), "Toolbox: Standard")
        self.assertEqual(self.model.current_toolbox().name, "Standard")
        self.model.set_default_toolbox("Standard")
        self.assertEqual(self.model.toolbox_line(), "Toolbox: Standard (default)")
        self.model.set_tool_offset(1, 9)
        self.assertEqual(self.model.toolbox_line(), "Toolbox: Standard (default, tools changed since)")
        again = project_from_json(project_to_json(self.model.project))
        self.assertEqual((again.program.toolbox_library, again.program.toolbox_name), (self.model.active_library_name("tools"), "Standard"))

    def test_a_new_project_from_the_default_toolbox_knows_it(self):
        self.model.save_toolbox(self.box())
        self.model.set_default_toolbox("Standard")
        self.model.new()
        self.assertEqual(self.model.toolbox_line(), "Toolbox: Standard (default)")

    def test_a_toolbox_of_another_library_is_named_but_not_current(self):
        self.model.save_toolbox(self.box())
        self.model.apply_toolbox("Standard")
        self.model.new_library("tools", "Other")
        self.assertIsNone(self.model.current_toolbox())
        self.assertIn("not in the library in use", self.model.toolbox_line())
        with self.assertRaises(Exception):
            self.model.make_current_toolbox_default()

    def test_the_tools_of_the_project_update_a_toolbox_or_make_a_new_one(self):
        self.model.save_toolbox(self.box())
        self.model.apply_toolbox("Standard")
        self.model.add_tool_from_library(self.names[2])
        self.model.save_project_tools_as_toolbox("Standard", update=True)
        self.assertEqual(len(self.model.toolboxes), 1)
        self.assertEqual(len(self.model.toolboxes[0].entries), 3)
        self.assertEqual(self.model.toolbox_line(), "Toolbox: Standard")
        with self.assertRaises(Exception):  # a new box may not take the name of one that is there
            self.model.save_project_tools_as_toolbox("Standard")
        self.model.save_project_tools_as_toolbox("Job 12")
        self.assertEqual(self.model.toolbox_line(), "Toolbox: Job 12")
        self.assertEqual(len(self.model.toolboxes), 2)

    def test_the_origin_of_a_tool_is_saved_with_the_project(self):
        self.model.save_toolbox(self.box())
        self.model.apply_toolbox("Standard")
        again = project_from_json(project_to_json(self.model.project))
        self.assertEqual([(t.origin_library, t.origin_name) for t in again.program.tools],
                         [(t.origin_library, t.origin_name) for t in self.model.program.tools])

    def test_a_tool_added_from_the_library_knows_where_it_came_from(self):
        number = self.model.add_tool_from_library(self.names[2])
        tool = self.model.program.tool(number)
        self.assertEqual((tool.origin_library, tool.origin_name), ("Example", self.names[2]))


class ChangeOfToolboxTests(RealProjectCase):
    def setUp(self):
        super().setUp()
        self.model.save_toolbox(self.box("A", (0, 1), (1, 2), (2, 3)))
        self.model.save_toolbox(self.box("B", (1, 1), (2, 2), (3, 3)))  # tool 2 of A is tool 1 of B, tool 3 of A is tool 2 of B
        self.model.apply_toolbox("A")
        for type_name, tool_number in (("facing", 1), ("turning", 2), ("drilling", 3), ("grooving", 3)):
            index = self.model.add_block(type_name)
            self.model.replace_block(index, replace(self.model.blocks[index], tool_number=tool_number))

    def test_the_report_tells_which_blocks_lose_their_tool_or_follow_it(self):
        change = self.model.toolbox_change("B")
        self.assertEqual((change.unhooked, change.renumbered, change.kept), ((0,), (1, 2, 3), ()))
        self.assertTrue(change.changes_blocks)
        self.assertFalse(self.model.toolbox_change("A").changes_blocks)

    def test_the_same_tool_of_the_same_library_follows_to_its_new_number_and_the_others_lose_it(self):
        self.model.apply_toolbox("B")
        self.assertEqual([b.tool_number for b in self.model.blocks], [NO_TOOL_NUMBER, 1, 2, 2])
        self.assertEqual([t.number for t in self.model.program.tools], [1, 2, 3])

    def test_a_box_of_another_library_unhooks_every_block(self):
        tools = [self.model.program.tool(n) for n in (1, 2, 3)]
        self.model.project = replace(self.model.project, program=replace(
            self.model.program, tools=tuple(replace(t, origin_library="Other shop") for t in tools),
        ))
        change = self.model.toolbox_change("A")
        self.assertEqual((change.unhooked, change.kept), ((0, 1, 2, 3), ()))
        self.model.apply_toolbox("A")
        self.assertEqual({b.tool_number for b in self.model.blocks}, {NO_TOOL_NUMBER})

    def test_a_tool_made_in_the_project_is_not_known_to_any_box(self):
        self.model.project = replace(self.model.project, program=replace(
            self.model.program, tools=tuple(replace(t, origin_library="", origin_name="") for t in self.model.program.tools),
        ))
        self.assertEqual(self.model.toolbox_change("A").unhooked, (0, 1, 2, 3))

    def test_a_change_can_be_undone(self):
        self.model.apply_toolbox("B")
        self.model.undo()
        self.assertEqual([b.tool_number for b in self.model.blocks], [1, 2, 3, 3])


if __name__ == "__main__":
    unittest.main()
