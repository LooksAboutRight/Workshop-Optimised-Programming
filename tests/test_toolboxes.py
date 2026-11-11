"""Toolboxes in the tool library (T17): the data, the library file, and the model that edits them."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from wop.adapters.library_files import read_library
from wop.core.files.app_settings import AppSettings, SettingsError
from wop.core.files.libraries import content_to_dict, with_content_from_dict, with_example_content
from wop.core.tooling.toolbox import (
    Toolbox,
    ToolboxEntry,
    ToolboxError,
    check_toolboxes,
    toolboxes_using,
    tools_of_toolbox,
    without_tool,
)
from wop.ui.app_model import AppModel, ModelError

ENTRY = ToolboxEntry


def example_tools():
    return with_example_content(AppSettings(), "tools").tools


def settings_with_boxes():
    tools = example_tools()
    standard = Toolbox("Standard", (ENTRY(tools[1].name, 2, 5), ENTRY(tools[0].name, 1)))
    return replace(with_example_content(AppSettings(), "tools"), toolboxes=(standard,), default_toolbox="Standard"), tools


class ToolboxDataTests(unittest.TestCase):
    def test_a_number_used_twice_a_tool_listed_twice_and_a_wrong_number_are_refused(self):
        with self.assertRaises(ToolboxError):
            Toolbox("a", (ENTRY("x", 1), ENTRY("y", 1)))
        with self.assertRaises(ToolboxError):
            Toolbox("a", (ENTRY("x", 1), ENTRY("X", 2)))
        for number in (0, -1, True):
            with self.assertRaises(ToolboxError):
                Toolbox("a", (ENTRY("x", number),))
        with self.assertRaises(ToolboxError):
            Toolbox("a", (ENTRY("x", 1, 0),))
        with self.assertRaises(ToolboxError):
            Toolbox(" ", ())

    def test_the_entries_are_listed_in_the_order_of_the_numbers(self):
        box = Toolbox("a", (ENTRY("c", 7), ENTRY("a", 1), ENTRY("b", 3)))
        self.assertEqual([e.number for e in box.entries], [1, 3, 7])

    def test_the_check_wants_known_tools_unique_names_and_an_existing_default(self):
        tools = example_tools()
        known = Toolbox("a", (ENTRY(tools[0].name, 1),))
        check_toolboxes((known,), "A", tools)  # names compare without case
        with self.assertRaises(ToolboxError):
            check_toolboxes((Toolbox("a", (ENTRY("no such tool", 1),)),), None, tools)
        with self.assertRaises(ToolboxError):
            check_toolboxes((known, Toolbox("A")), None, tools)
        with self.assertRaises(ToolboxError):
            check_toolboxes((known,), "other", tools)

    def test_the_tools_of_a_box_carry_its_numbers_and_offsets_in_the_order_of_the_numbers(self):
        settings, tools = settings_with_boxes()
        made = tools_of_toolbox(settings.toolboxes[0], tools)
        self.assertEqual([(t.name, t.number, t.offset_number) for t in made], [(tools[0].name, 1, None), (tools[1].name, 2, 5)])

    def test_using_and_taking_a_tool_out(self):
        settings, tools = settings_with_boxes()
        self.assertEqual(toolboxes_using(settings.toolboxes, tools[0].name.upper()), ("Standard",))
        self.assertEqual(toolboxes_using(settings.toolboxes, tools[2].name), ())
        emptied = without_tool(settings.toolboxes, tools[0].name)
        self.assertEqual([e.tool_name for e in emptied[0].entries], [tools[1].name])


class ToolboxFileTests(unittest.TestCase):
    def test_the_boxes_and_the_default_round_trip_through_the_library_data(self):
        settings, _tools = settings_with_boxes()
        data = content_to_dict(settings, "tools")
        again = with_content_from_dict(AppSettings(), "tools", data)
        self.assertEqual(again.toolboxes, settings.toolboxes)
        self.assertEqual(again.default_toolbox, "Standard")

    def test_a_library_file_without_boxes_loads_with_none(self):
        data = content_to_dict(with_example_content(AppSettings(), "tools"), "tools")
        data.pop("toolboxes")
        again = with_content_from_dict(AppSettings(), "tools", data)
        self.assertEqual((again.toolboxes, again.default_toolbox), ((), None))

    def test_a_box_that_names_a_missing_tool_makes_the_file_unusable(self):
        settings, _tools = settings_with_boxes()
        data = content_to_dict(settings, "tools")
        data["toolboxes"][0]["tools"][0]["tool"] = "gone"
        with self.assertRaises(SettingsError):
            with_content_from_dict(AppSettings(), "tools", data)

    def test_the_example_library_has_no_boxes(self):
        settings, _tools = settings_with_boxes()
        example = with_example_content(settings, "tools")
        self.assertEqual((example.toolboxes, example.default_toolbox), ((), None))


class ToolboxModelTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.settings_path = Path(self._folder.name) / "settings.json"
        self.model = AppModel(settings_path=self.settings_path)
        self.names = [t.name for t in self.model.tool_library]

    def test_a_box_is_saved_with_the_library_and_the_example_forks(self):
        self.assertEqual(self.model.active_library_name("tools"), "Example")
        self.model.save_toolbox(Toolbox("Standard", (ENTRY(self.names[0], 1), ENTRY(self.names[1], 4, 4))))
        self.assertNotEqual(self.model.active_library_name("tools"), "Example")
        data = read_library(self.settings_path, "tools", self.model.active_library_name("tools"))
        self.assertEqual(data["toolboxes"][0]["name"], "Standard")
        again = AppModel(settings_path=self.settings_path)
        self.assertEqual(again.toolboxes, self.model.toolboxes)

    def test_rename_keeps_the_default_and_a_clash_is_refused(self):
        self.model.save_toolbox(Toolbox("a", (ENTRY(self.names[0], 1),)))
        self.model.save_toolbox(Toolbox("b"))
        self.model.set_default_toolbox("a")
        self.model.save_toolbox(Toolbox("z", (ENTRY(self.names[0], 1),)), old_name="a")
        self.assertEqual(self.model.default_toolbox, "z")
        with self.assertRaises(ModelError):
            self.model.save_toolbox(Toolbox("B"), old_name="z")

    def test_a_box_with_an_unknown_tool_is_refused(self):
        with self.assertRaises(ModelError):
            self.model.save_toolbox(Toolbox("a", (ENTRY("no such tool", 1),)))

    def test_deleting_the_default_box_leaves_no_default(self):
        self.model.save_toolbox(Toolbox("a"))
        self.model.set_default_toolbox("a")
        self.model.delete_toolbox("a")
        self.assertEqual((self.model.toolboxes, self.model.default_toolbox), ((), None))
        with self.assertRaises(ModelError):
            self.model.set_default_toolbox("a")
        with self.assertRaises(ModelError):
            self.model.delete_toolbox("a")

    def test_a_tool_in_a_box_is_deleted_only_with_the_box_entries(self):
        self.model.save_toolbox(Toolbox("a", (ENTRY(self.names[0], 1), ENTRY(self.names[1], 2))))
        self.assertEqual(self.model.toolboxes_using_tool(self.names[0]), ("a",))
        with self.assertRaises(ModelError):
            self.model.remove_tool_from_library(self.names[0])
        self.model.remove_tool_from_library(self.names[0], from_toolboxes=True)
        self.assertEqual([e.tool_name for e in self.model.toolboxes[0].entries], [self.names[1]])

    def test_switching_the_library_switches_the_boxes(self):
        self.model.save_toolbox(Toolbox("a", (ENTRY(self.names[0], 1),)))
        self.model.switch_library("tools", "Example")
        self.assertEqual(self.model.toolboxes, ())


if __name__ == "__main__":
    unittest.main()
