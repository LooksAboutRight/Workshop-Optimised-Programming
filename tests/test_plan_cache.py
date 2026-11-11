"""The plan of a program is worked out once for the same program: the analysis, the export and the G-code share it."""

import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent


class PlanCacheTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel
        from wop.ui.model import views

        self.views = views
        self.model = AppModel()
        self.model.open(ROOT / "examples" / "reference.wop.json")
        self.real = views.plan_program

    def counting(self):
        calls = []

        def plan(*args, **kwargs):
            calls.append(kwargs)
            return self.real(*args, **kwargs)

        return mock.patch.object(self.views, "plan_program", side_effect=plan), calls

    def test_the_export_uses_the_plan_of_the_analysis(self):
        patch, calls = self.counting()
        with patch:
            self.model.gcode()
            self.model.gcode(accept_all=True)
            self.model.export_report()
        self.assertEqual(calls, [])  # the analysis made after opening the file is reused

    def test_a_change_of_the_program_makes_a_new_plan(self):
        patch, calls = self.counting()
        with patch:
            self.model.add_block("facing")
            self.model.gcode()
            self.model.gcode()
        self.assertEqual(len(calls), 1)  # one plan for the changed program, shared by the analysis and the two exports

    def test_the_same_text_comes_out_each_time(self):
        first = self.model.gcode().text
        self.model.refresh()
        self.assertEqual(self.model.gcode().text, first)

    def test_a_selection_has_its_own_plan_and_the_choice_of_done_matters(self):
        patch, calls = self.counting()
        with patch:
            self.model.gcode(selection=(1,))
            self.model.gcode(selection=(1,))
            self.model.gcode(selection=(1,), unticked_done=False)
            self.model.gcode()
        self.assertEqual(len(calls), 2)  # (1,) with done, (1,) with not done; the whole program came from the analysis

    def test_the_text_of_a_selection_does_not_depend_on_what_was_cached(self):
        whole = self.model.gcode().text
        part = self.model.gcode(selection=(1,)).text
        self.assertNotEqual(whole, part)
        self.assertEqual(self.model.gcode().text, whole)


if __name__ == "__main__":
    unittest.main()
