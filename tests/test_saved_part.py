"""The finished part saved in the project file (V9): written with the project, shown at once when the file is opened, until the plan of the
background work is there."""

import json
import tempfile
import unittest
from pathlib import Path

from wop.adapters.project_files import load_project_and_preview
from wop.ui.app_constants import WORKING_PLANNING
from wop.ui.app_model import AppModel

ROOT = Path(__file__).resolve().parent.parent


class HeldRunner:
    """Keeps the background jobs until the test runs them."""

    def __init__(self):
        self.jobs = []

    def __call__(self, job, done):
        self.jobs.append((job, done))

    def run_all(self):
        while self.jobs:
            job, done = self.jobs.pop(0)
            done(job())


class SavedPartTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.model = AppModel()
        self.model.open(ROOT / "examples" / "reference.wop.json")
        self.saved = self.folder / "saved.wop.json"
        self.model.save(self.saved)

    def opened_in_the_background(self, path):
        model, runner = AppModel(), HeldRunner()
        model.run_in_background(runner)
        model.open(path)
        return model, runner

    def test_the_part_of_the_plan_is_saved_and_reads_back_exactly(self):
        _project, loops = load_project_and_preview(self.saved)
        self.assertEqual([tuple(loop) for loop in loops], [tuple(loop) for loop in self.model._finished_part()])

    def test_the_saved_part_is_shown_at_once_and_the_plan_replaces_it(self):
        model, runner = self.opened_in_the_background(self.saved)
        self.assertIsNone(model.analysis.plan)
        self.assertEqual(model.analysis.working, WORKING_PLANNING)
        self.assertTrue(model.picture())  # the saved part, before any plan
        self.assertIsNotNone(model.scene3d())
        self.assertAlmostEqual(model.analysis.preview.area, self.model.analysis.plan.final_residual.area, places=6)
        runner.run_all()
        self.assertIsNotNone(model.analysis.plan)
        self.assertIsNone(model.analysis.preview)
        self.assertEqual(model.picture(), self.model.picture())

    def test_a_file_without_a_saved_part_waits_for_the_plan(self):
        model, runner = self.opened_in_the_background(ROOT / "examples" / "reference.wop.json")  # the example tools write no part
        self.assertEqual(model.picture(), "")
        runner.run_all()
        self.assertTrue(model.picture())

    def test_a_part_that_does_not_read_is_left_out(self):
        data = json.loads(self.saved.read_text(encoding="utf-8"))
        data["preview"] = [["L 1 2"], ["something else"]]
        self.saved.write_text(json.dumps(data), encoding="utf-8")
        model, runner = self.opened_in_the_background(self.saved)
        self.assertIsNone(model.analysis.preview)
        runner.run_all()
        self.assertIsNotNone(model.analysis.plan)

    def test_no_part_is_saved_while_the_plan_of_a_change_is_being_made(self):
        model, runner = self.opened_in_the_background(self.saved)
        runner.run_all()
        model.add_block("facing")  # planned in the background: the shown plan is the one before the change
        again = self.folder / "again.wop.json"
        model.save(again)
        self.assertNotIn('"preview"', again.read_text(encoding="utf-8"))
        runner.run_all()
        model.save(again)
        self.assertIn('"preview"', again.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
