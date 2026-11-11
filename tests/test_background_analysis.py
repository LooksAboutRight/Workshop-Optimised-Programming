"""Planning and checking in the background (`AppModel.run_in_background`, wop/ui/qt/background.py): the shown analysis stays until
the new plan is there, the findings follow, a newer change throws an older result away, and an export never uses an older plan."""

import os
import sys
import time
import unittest
from pathlib import Path

from tests.helpers import project_path
from wop.ui.app_constants import WORKING_CHECKING, WORKING_PLANNING
from wop.ui.app_model import AppModel

ROOT = Path(__file__).resolve().parent.parent


class HeldRunner:
    """A runner that keeps the jobs until the test runs them (one at a time, oldest first)."""

    def __init__(self):
        self.jobs = []

    def __call__(self, job, done):
        self.jobs.append((job, done))

    def run_next(self):
        job, done = self.jobs.pop(0)
        done(job())

    def run_all(self):
        while self.jobs:
            self.run_next()


def background_model(project="collision_demo.wop.json"):
    model = AppModel()
    model.open(project_path(project))
    model.auto_check = True
    runner = HeldRunner()
    model.run_in_background(runner)
    told = []
    model.subscribe_results(lambda: told.append(model.analysis.working))
    return model, runner, told


class BackgroundAnalysisTests(unittest.TestCase):
    def test_the_old_analysis_stays_until_the_plan_is_there_and_the_findings_follow(self):
        model, runner, told = background_model()
        before = model.analysis
        model.add_block("facing")
        self.assertEqual(model.analysis.working, WORKING_PLANNING)
        self.assertIs(model.analysis.plan, before.plan)  # the picture shows the old plan meanwhile
        runner.run_next()  # the plan
        self.assertEqual(model.analysis.working, WORKING_CHECKING)
        self.assertIs(model.analysis.program, model.program)
        self.assertEqual(model.analysis.findings, [])
        runner.run_next()  # the check
        self.assertEqual(model.analysis.working, "")
        self.assertTrue(model.analysis.checked)
        self.assertEqual(told, [WORKING_CHECKING, ""])
        model.run_in_background(None)
        self.assertEqual(model.analysis.findings, model.refresh().findings)  # the same as planned and checked at once

    def test_a_newer_change_throws_the_older_result_away(self):
        model, runner, told = background_model()
        model.add_block("facing")
        model.add_block("turning")
        runner.run_all()
        self.assertIs(model.analysis.program, model.program)
        self.assertEqual(told, [WORKING_CHECKING, ""])  # only the newest program was shown
        self.assertEqual(len(model.analysis.plan.blocks) + len(model.analysis.plan.left_out), len(model.blocks))

    def test_the_older_work_stops_between_two_blocks(self):
        model, runner, _told = background_model("reference.wop.json")
        model.add_block("facing")
        model.add_block("turning")
        older_job, older_done = runner.jobs.pop(0)
        self.assertIsNone(older_job())  # asked to stop before its first block: no result
        runner.run_all()
        self.assertIs(model.analysis.program, model.program)

    def test_an_export_while_the_work_is_running_uses_the_program_as_it_is(self):
        model, runner, _told = background_model()
        model.add_block("facing")
        report = model.export_report(run_check=True)
        self.assertIs(model.analysis.program, model.program)
        self.assertEqual(model.analysis.working, "")
        self.assertTrue(report.checked)
        runner.run_all()  # what was still waiting is not used any more
        self.assertIs(model.analysis.program, model.program)
        self.assertEqual(model.analysis.working, "")

    def test_without_the_automatic_check_only_the_plan_is_made(self):
        model, runner, told = background_model()
        model.auto_check = False
        model.refresh()  # the plan again, now without the check
        runner.run_all()
        self.assertFalse(model.analysis.checked)
        self.assertEqual(model.analysis.working, "")
        self.assertEqual(told, [""])


try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class QtRunnerTests(unittest.TestCase):
    def test_the_result_comes_back_in_the_window_thread(self):
        import threading

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from wop.ui.qt.background import BackgroundRunner

        application = QApplication.instance() or QApplication([])
        runner = BackgroundRunner()
        threads = []
        runner.start(lambda: threading.current_thread(), lambda result: threads.append((result, threading.current_thread())))
        deadline = time.monotonic() + 10
        while not threads and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)
        self.assertEqual(len(threads), 1)
        job_thread, done_thread = threads[0]
        self.assertIsNot(job_thread, threading.main_thread())
        self.assertIs(done_thread, threading.main_thread())

    def test_the_window_shows_the_work_and_then_the_result(self):
        import tempfile

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from wop.ui.qt.background import BackgroundRunner
        from wop.ui.qt.main_window import MainWindow

        application = QApplication.instance() or QApplication([])
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        model = AppModel(settings_path=Path(folder.name) / "settings.json")
        model.open(ROOT / "tests" / "data" / "projects" / "collision_demo.wop.json")
        model.auto_check = True
        window = MainWindow(model)
        self.addCleanup(lambda: (setattr(model, "dirty", False), window.close()))  # no question about saving at the end
        model.run_in_background(BackgroundRunner(window).start)
        model.add_block("facing")
        self.assertTrue(window._work_label.text())  # planning ...
        deadline = time.monotonic() + 120
        while model.analysis.working and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)
        application.processEvents()
        self.assertEqual(model.analysis.working, "")
        self.assertIs(model.analysis.program, model.program)
        self.assertEqual(window._work_label.text(), "")
        self.assertIn("COLLISION", window.messages.toPlainText())  # the demo collides


if __name__ == "__main__":
    unittest.main()
