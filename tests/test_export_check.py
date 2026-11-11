"""The check before the export: what the model knows (`export_report`) and the window that asks (real PySide6, offscreen)."""

import os
import sys
import unittest
from pathlib import Path


try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog

    APP = QApplication.instance() or QApplication([])

ROOT = Path(__file__).parent.parent

from tests.helpers import project_path  # noqa: E402


def model_with(example, auto_check=True):
    from wop.ui.app_model import AppModel

    model = AppModel()
    model.auto_check = auto_check
    model.open(project_path(example))
    return model


class ExportReportTests(unittest.TestCase):
    def test_checks_on_and_nothing_found(self):
        report = model_with("reference.wop.json").export_report()
        self.assertEqual((report.checked, report.problems), (True, ()))

    def test_checks_on_and_a_collision(self):
        report = model_with("collision_demo.wop.json").export_report()
        self.assertTrue(report.checked)
        self.assertTrue(any("jaws" in problem for problem in report.problems))

    def test_checks_off_means_not_checked_and_no_findings_yet(self):
        model = model_with("collision_demo.wop.json", auto_check=False)
        report = model.export_report()
        self.assertFalse(report.checked)
        self.assertFalse(any("jaws" in problem for problem in report.problems))

    def test_running_the_checks_finds_them(self):
        model = model_with("collision_demo.wop.json", auto_check=False)
        report = model.export_report(run_check=True)
        self.assertTrue(report.checked)
        self.assertTrue(any("jaws" in problem for problem in report.problems))

    def test_a_block_that_is_left_out_is_listed_without_any_check(self):
        model = model_with("reference.wop.json", auto_check=False)
        model.add_block("turning_contour")  # no contour: the block is left out
        report = model.export_report()
        self.assertFalse(report.checked)
        self.assertTrue(report.problems)

    def test_a_selection_follows_the_automatic_check_too(self):
        off = model_with("collision_demo.wop.json", auto_check=False)
        self.assertFalse(off.export_report((0,)).checked)
        self.assertFalse(off.selection_analysis((0,)).checked)
        self.assertTrue(off.export_report((0,), run_check=True).problems)
        on = model_with("collision_demo.wop.json", auto_check=True)
        self.assertTrue(on.export_report((0,)).checked)
        self.assertTrue(on.export_report((0,)).problems)

    def test_export_problems_still_runs_the_check(self):
        model = model_with("collision_demo.wop.json", auto_check=False)
        self.assertTrue(model.export_problems())


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class ExportCheckDialogTests(unittest.TestCase):
    def make(self, report, run=None):
        from wop.ui.qt.dialogs import ExportCheckDialog

        dialog = ExportCheckDialog(None, report, run or (lambda: report))
        self.addCleanup(dialog.deleteLater)
        return dialog

    def report(self, checked, *problems):
        from wop.ui.app_model import ExportReport

        return ExportReport(checked, tuple(problems))

    def test_checks_off_says_so_and_offers_the_three_buttons(self):
        dialog = self.make(self.report(False))
        self.assertIn("No collision and power checks", dialog._heading.text())
        self.assertFalse(dialog._run.isHidden())
        self.assertEqual(dialog._export.text(), "Export without checks")
        self.assertTrue(dialog._list.isHidden())

    def test_checks_off_and_a_block_left_out_lists_it(self):
        dialog = self.make(self.report(False, "block 3 is left out"))
        self.assertFalse(dialog._list.isHidden())
        self.assertIn("block 3 is left out", dialog._list.toPlainText())
        self.assertIn("left out", dialog._heading.text())

    def test_findings_offer_export_anyway_and_no_run_button(self):
        dialog = self.make(self.report(True, "collision A", "collision B"))
        self.assertIn("2 problem(s)", dialog._heading.text())
        self.assertEqual(dialog._export.text(), "Export anyway")
        self.assertTrue(dialog._run.isHidden())
        self.assertIn("collision B", dialog._list.toPlainText())

    def test_running_the_checks_with_nothing_found_goes_on_to_the_export(self):
        dialog = self.make(self.report(False), run=lambda: self.report(True))
        dialog._run_now()
        self.assertEqual(dialog.result(), QDialog.Accepted)

    def test_running_the_checks_with_findings_shows_them_and_waits(self):
        dialog = self.make(self.report(False), run=lambda: self.report(True, "collision A"))
        dialog._run_now()
        self.assertNotEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog._export.text(), "Export anyway")
        self.assertTrue(dialog._run.isHidden())
        self.assertIn("collision A", dialog._list.toPlainText())

    def test_the_preview_of_export_selected_offers_run_checks_only_when_given_a_way_to(self):
        from wop.ui.qt.dialogs import ExportSelectedDialog

        runs = []

        def build(done):
            return "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>", "notes", "code"

        offered = ExportSelectedDialog(None, "t", build, lambda done: None, True, lambda: runs.append(1))
        self.addCleanup(offered.deleteLater)
        self.assertFalse(offered._run_button.isHidden())
        offered._run_button.click()
        self.assertEqual(runs, [1])
        self.assertTrue(offered._run_button.isHidden())
        plain = ExportSelectedDialog(None, "t", build, lambda done: None, True)
        self.addCleanup(plain.deleteLater)
        self.assertTrue(plain._run_button.isHidden())

    def test_export_without_checks_accepts_and_cancel_rejects(self):
        dialog = self.make(self.report(False))
        dialog._export.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        other = self.make(self.report(False))
        other.reject()
        self.assertEqual(other.result(), QDialog.Rejected)


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class ConfirmExportTests(unittest.TestCase):
    """The main window asks only when it must: checks done and nothing found: no window."""

    def window(self, example, auto_check):
        from wop.ui.qt.main_window import MainWindow

        window = MainWindow(model_with(example, auto_check))
        self.addCleanup(window.deleteLater)
        return window

    def test_checks_on_and_nothing_found_does_not_ask(self):
        from unittest import mock

        window = self.window("reference.wop.json", True)
        with mock.patch("wop.ui.qt.window_parts.files.ExportCheckDialog", side_effect=AssertionError("must not open")):
            self.assertTrue(window._confirm_export(None, True))

    def test_checks_off_always_asks_and_the_answer_decides(self):
        from unittest import mock

        window = self.window("reference.wop.json", False)
        for answer in (QDialog.Accepted, QDialog.Rejected):
            with mock.patch("wop.ui.qt.window_parts.files.ExportCheckDialog") as dialog:
                dialog.return_value.exec.return_value = answer
                self.assertEqual(window._confirm_export(None, True), answer == QDialog.Accepted)
                self.assertFalse(dialog.call_args.args[1].checked)

    def test_findings_ask_even_with_checks_on(self):
        from unittest import mock

        window = self.window("collision_demo.wop.json", True)
        with mock.patch("wop.ui.qt.window_parts.files.ExportCheckDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.Rejected
            self.assertFalse(window._confirm_export(None, True))
            self.assertTrue(dialog.call_args.args[1].problems)


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class MachinesDialogOpensAtTheProjectMachineTests(unittest.TestCase):
    """The post of the project is the post of its machine: the dialog must open on that machine, not on the default one."""

    def test_it_opens_on_the_machine_of_the_project(self):
        import tempfile

        from wop.ui.app_model import AppModel
        from wop.ui.qt.machines_dialog import MachinesDialog

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        model = AppModel(settings_path=Path(folder.name) / "settings.json")
        first, second = model.new_machine(), model.new_machine()
        model.set_default_machine(first)
        model.use_machine(second)
        dialog = MachinesDialog(None, model)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog._name, second)

    def test_without_a_machine_in_the_project_it_opens_on_the_default_one(self):
        import tempfile

        from wop.ui.app_model import AppModel
        from wop.ui.qt.machines_dialog import MachinesDialog

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        model = AppModel(settings_path=Path(folder.name) / "settings.json")
        first, _second = model.new_machine(), model.new_machine()
        model.set_default_machine(first)
        model.use_machine(None)
        dialog = MachinesDialog(None, model)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog._name, first)


if __name__ == "__main__":
    unittest.main()
