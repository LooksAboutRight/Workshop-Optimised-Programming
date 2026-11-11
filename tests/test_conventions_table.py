import importlib
import json
import tempfile
import unittest
from pathlib import Path

from wop.core.files import convention_overrides
from wop.core.conventions import CONVENTIONS, GROUPS


class TableTests(unittest.TestCase):
    def test_every_entry_names_a_constant_that_exists(self):
        for convention in CONVENTIONS:
            with self.subTest(name=convention.name):
                self.assertTrue(hasattr(importlib.import_module(convention.module), convention.name))

    def test_names_are_unique_and_groups_known(self):
        names = [c.name for c in CONVENTIONS]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(c.group in GROUPS and c.meaning for c in CONVENTIONS))


class OverrideTests(unittest.TestCase):
    def _apply(self, data, namespace, module="wop.core.constants"):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "conventions.json"
            path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
            before = len(convention_overrides.problems())
            replaced = convention_overrides.apply_overrides(namespace, module, path)
            return replaced, convention_overrides.problems()[before:]

    def test_a_value_of_the_file_replaces_the_default(self):
        namespace = {"GROOVE_ONE_SIDED_CUT_MM": 1.0, "THREAD_SPRING_PASSES": 1}
        replaced, problems = self._apply({"GROOVE_ONE_SIDED_CUT_MM": 1.5, "THREAD_SPRING_PASSES": 2.0}, namespace)
        self.assertEqual(namespace, {"GROOVE_ONE_SIDED_CUT_MM": 1.5, "THREAD_SPRING_PASSES": 2})
        self.assertEqual(replaced, {"GROOVE_ONE_SIDED_CUT_MM": 1.0, "THREAD_SPRING_PASSES": 1})
        self.assertEqual(problems, [])

    def test_wrong_things_are_ignored_and_reported(self):
        namespace = {"GROOVE_ONE_SIDED_CUT_MM": 1.0}
        _replaced, problems = self._apply({"GROOVE_ONE_SIDED_CUT_MM": "wide", "NO_SUCH_THING": 3}, namespace)
        self.assertEqual(namespace["GROOVE_ONE_SIDED_CUT_MM"], 1.0)
        self.assertEqual(len(problems), 2)

    def test_a_broken_file_changes_nothing(self):
        namespace = {"GROOVE_ONE_SIDED_CUT_MM": 1.0}
        replaced, problems = self._apply("{not json", namespace)
        self.assertEqual((replaced, namespace["GROOVE_ONE_SIDED_CUT_MM"]), ({}, 1.0))
        self.assertEqual(len(problems), 1)

    def test_a_name_of_another_module_is_not_applied_here(self):
        namespace = {"UNDO_LIMIT": 200}
        replaced, _problems = self._apply({"UNDO_LIMIT": 50}, namespace)  # UNDO_LIMIT belongs to the application constants
        self.assertEqual((replaced, namespace["UNDO_LIMIT"]), ({}, 200))

    def test_no_file_is_no_problem(self):
        self.assertEqual(convention_overrides.apply_overrides({}, "wop.core.constants", Path("no/such/conventions.json")), {})


class NoseRadiusPresetTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel

        self.model = AppModel()
        self.with_nose = None
        for type_name, _label in self.model.tool_type_choices():
            number = self.model.add_tool_of_type(type_name)
            if self.model.program.tool(number).nose_radius_mm > 0 and self.with_nose is None:
                self.with_nose = number

    def test_a_new_turning_block_takes_the_finishing_allowance_from_the_nose_radius_but_not_the_depth_of_cut(self):
        from dataclasses import replace

        from wop.core.constants import EXAMPLE_DEPTH_OF_CUT_MM, TURNING_FINISH_ALLOWANCE_NOSE_FACTOR

        index = self.model.add_block("turning")
        block = self.model.blocks[index]
        self.model.replace_block(index, replace(block, tool_number=self.with_nose))
        nose = self.model.program.tool(self.with_nose).nose_radius_mm
        block = self.model.blocks[index]
        self.assertAlmostEqual(block.finish_allowance_mm, TURNING_FINISH_ALLOWANCE_NOSE_FACTOR * nose)
        self.assertEqual(block.depth_of_cut_mm, EXAMPLE_DEPTH_OF_CUT_MM)

    def test_a_tool_without_nose_radius_leaves_the_example_values(self):
        from wop.core.constants import EXAMPLE_DEPTH_OF_CUT_MM

        index = self.model.add_block("turning")
        block = self.model.blocks[index]
        if self.model.program.tool(block.tool_number).nose_radius_mm == 0:
            self.assertEqual(block.depth_of_cut_mm, EXAMPLE_DEPTH_OF_CUT_MM)
