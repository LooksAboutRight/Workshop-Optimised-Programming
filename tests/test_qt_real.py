"""The Qt code with the real PySide6, offscreen: walk through the window and build every dialog and view.

`tests/test_qt_smoke.py` does the same with a stand-in, but only when PySide6 is not installed, so on a PC with the real
PySide6 most Qt modules had no test at all. These tests find wrong names, wrong arguments, broken signal wiring and
exceptions in the window code; they say nothing about how it looks. (A Python error inside a slot is only printed by Qt,
not raised: the walk calls the model and the window directly so that an error reaches the test.)
"""

import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    APP = QApplication.instance() or QApplication([])

ROOT = Path(__file__).parent.parent


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class WindowWalkTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel
        from wop.ui.qt.main_window import MainWindow

        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")
        self.model.open(ROOT / "examples" / "reference.wop.json")
        self.window = MainWindow(self.model)
        self.addCleanup(self.window.deleteLater)
        self.window.show()
        APP.processEvents()

    def test_the_path_dialog_takes_a_feed_for_the_selected_piece_and_refuses_a_bad_one(self):
        from wop.ui.qt.sketch_dialog import SketchDialog

        from wop.core.blocks.custom_path import CustomPathBlock

        index = self.model.add_block("custom_path")
        block = self.model.blocks[index]
        sample = CustomPathBlock.sample(block.block_id, block.tool_number, block.spindle)
        self.model.replace_block(index, replace(block, sketch=sample.sketch))
        dialog = SketchDialog(self.window, target=self.model.path_sketch_target(index))
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.feed_row.isHidden())
        session = dialog.session
        piece = next(i for i in session.sketch.lines if i not in session.sketch.rapid_pieces and not session.sketch.is_locked_piece(i))
        self.assertFalse(dialog.feed_edit.isEnabled())
        session.selected_pieces = {piece}
        session.refresh()
        self.assertTrue(dialog.feed_edit.isEnabled())
        dialog.feed_edit.setText("0,25")
        dialog._feed_edited()
        self.assertEqual(session.sketch.piece_feeds, {piece: 0.25})
        dialog.feed_edit.setText("-1")
        dialog._feed_edited()
        self.assertEqual(session.sketch.piece_feeds, {piece: 0.25})
        self.assertIn("greater than zero", session.message)
        dialog.feed_edit.setText("")
        dialog._feed_edited()
        self.assertEqual(session.sketch.piece_feeds, {})

    def test_the_path_dialog_steps_with_its_buttons_and_the_arrow_keys(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent

        from wop.core.blocks.custom_path import CustomPathBlock
        from wop.ui.qt.sketch_dialog import SketchDialog

        index = self.model.add_block("custom_path")
        block = self.model.blocks[index]
        sample = CustomPathBlock.sample(block.block_id, block.tool_number, block.spindle)
        self.model.replace_block(index, replace(block, sketch=sample.sketch))
        dialog = SketchDialog(self.window, target=self.model.path_sketch_target(index))
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.step_row.isHidden())
        session = dialog.session
        self.assertIsNone(session.step)
        dialog.forward_button.click()
        self.assertEqual(session.step, 0)
        self.assertIn("Step 1 of", dialog.step_label.text())
        for key, expected in ((Qt.Key_Right, 1), (Qt.Key_Right, 2), (Qt.Key_Left, 1)):
            dialog.canvas.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
            self.assertEqual(session.step, expected)
        dialog.back_button.click()
        dialog.back_button.click()
        self.assertIsNone(session.step)
        dialog.canvas.repaint()  # the picture draws the stepped state without an error
        session.step_forward()
        dialog.canvas.repaint()

    def test_a_raw_part_dialog_has_no_feed_row(self):
        from wop.ui.qt.sketch_dialog import SketchDialog

        dialog = SketchDialog(self.window, target=self.model.raw_part_sketch_target())
        self.addCleanup(dialog.deleteLater)
        self.assertTrue(dialog.feed_row.isHidden())

    def test_the_greyed_start_z_shows_what_auto_worked_out(self):
        self.model.refresh()  # at once, not in the background: the results are there
        self.model.select(2)  # block 3 of the reference project starts behind the step of block 2 (Z -30)
        self.window._fill_flow()
        self.window._show_form()
        box = self.window.form._widgets[("start_z_mm",)]
        self.assertFalse(box.isEnabled())
        self.assertAlmostEqual(box.value(), -30)
        self.window.form.show_greyed(replace(self.model.blocks[2], start_z_mm=-25))  # a new plan arrives: the field follows, no rebuild
        self.assertIs(self.window.form._widgets[("start_z_mm",)], box)
        self.assertAlmostEqual(box.value(), -25)

    def test_the_gcode_folder_is_apart_from_the_folder_of_the_projects(self):
        with tempfile.TemporaryDirectory() as projects, tempfile.TemporaryDirectory() as gcode:
            self.window._chosen(str(Path(projects) / "part.wop.json"))
            self.window._chosen(str(Path(gcode) / "part.ngc"), export=True)
            self.assertEqual(self.window._dialog_start("x.json"), str(Path(projects) / "x.json"))
            self.assertEqual(self.window._dialog_start("x.ngc", export=True), str(Path(gcode) / "x.ngc"))

    def test_the_gcode_file_is_named_after_the_project(self):
        self.model.project = replace(self.model.project, touched=())  # nothing touched: the title is a preset
        self.model.path = Path("C:/parts/shaft 12.wop.json")
        self.assertEqual(self.window._gcode_name(), "shaft 12")
        self.model.path = Path("C:/parts/g53 example.json")
        self.assertEqual(self.window._gcode_name(), "g53 example")  # .json goes too
        self.model.path = None
        self.assertTrue(self.window._gcode_name())

    def test_the_gcode_file_is_named_after_the_title_when_the_user_gave_one(self):
        self.model.project = replace(self.model.project, touched=())
        self.model.path = Path("C:/parts/shaft 12.wop.json")
        from wop.core.program_model.touched import SETUP_OWNER

        self.model.set_touched(SETUP_OWNER, ("title",))
        self.model.project = replace(self.model.project, settings=replace(self.model.project.settings, title="Flange A"))
        self.assertEqual(self.window._gcode_name(), "Flange A")
        self.model.set_touched(SETUP_OWNER, ("title",), False)
        self.assertEqual(self.window._gcode_name(), "shaft 12")

    def test_every_block_type_can_be_added_and_chosen(self):
        from wop.core.blocks.base import BLOCK_TYPES

        for name in BLOCK_TYPES.names():
            with self.subTest(block=name):
                index = self.model.add_block(name)
                self.model.select(index)
                APP.processEvents()
                self.assertIsNotNone(self.window.form)

    def test_setup_and_every_block_of_the_reference_project_can_be_chosen(self):
        self.model.select(None)
        APP.processEvents()
        for index in range(len(self.model.blocks)):
            self.model.select(index)
            APP.processEvents()

    def test_the_centre_views_and_the_3d_toggle(self):
        self.model.show_tools()
        APP.processEvents()
        self.model.show_workholding()
        APP.processEvents()
        self.model.select(1)
        APP.processEvents()
        self.assertTrue(self.model.picture())

    def test_zooming_the_2d_picture_draws_it_again_with_thinner_lines(self):
        from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtTest import QTest
        from wop.ui.qt.qt_constants import ZOOM_REDRAW_DELAY_MS

        ZOOM_WAIT_STEPS = 30  # at most 30 waits of one redraw delay (3 s)

        centre = self.window.centre
        centre.button_2d.setChecked(True)
        centre.redraw()
        picture = centre.picture
        drawn = []
        original = self.model.picture
        self.model.picture = lambda *a, **k: drawn.append(k.get("line_scale")) or original(*a, **k)
        self.addCleanup(setattr, self.model, "picture", original)
        wheel = QWheelEvent(QPointF(100, 100), QPointF(100, 100), QPoint(0, 0), QPoint(0, 120), Qt.NoButton,
                            Qt.NoModifier, Qt.NoScrollPhase, False)
        for _ in range(5):
            picture.wheelEvent(wheel)
        self.assertLess(picture.line_scale(), 1.0)
        self.assertEqual(drawn, [])  # not while the wheel turns

        def wait_for(count: int) -> None:
            """Wait until the picture was drawn `count` times. One fixed wait is not enough: after other tests of this module the offscreen
            event loop sometimes does not serve the timer of the picture before another timer is started (a window of the test, not of the program)."""
            for _ in range(ZOOM_WAIT_STEPS):
                if len(drawn) >= count:
                    return
                QTest.qWait(ZOOM_REDRAW_DELAY_MS)
                QTimer.singleShot(0, lambda: None)  # a new timer makes the event loop look at all of them

        wait_for(1)
        self.assertEqual(drawn, [picture.line_scale()])
        picture.reset_view()
        wait_for(2)
        self.assertEqual(drawn[-1], 1.0)

    def test_the_step_through_follows_every_move(self):
        stepper = self.model.stepper()
        self.assertIsNotNone(stepper)
        self.model.select(1)
        for step in range(0, len(stepper.frames), max(1, len(stepper.frames) // 12)):
            self.model.step_view(step)

    def test_a_new_contour_opens_the_sketch_editor_and_stays_chosen_when_it_is_closed(self):
        opened = []

        class FakeSketchDialog:
            def __init__(self, parent, target=None):
                opened.append(target)

            def exec(self):
                return 0  # closed at once

        with mock.patch("wop.ui.qt.window_parts.actions.SketchDialog", FakeSketchDialog):
            self.window._new_contour()
        APP.processEvents()
        self.assertEqual(len(opened), 1)
        self.assertEqual(self.model.selected_contour, self.model.program.contours[-1].contour_id)
        self.assertEqual(self.window.right_stack.currentIndex(), 1)  # the panel with the name and the Sketch editor button
        self.window.contour_panel._name.setText("Shaft")
        self.window.contour_panel._name_changed()
        self.assertEqual(self.model.chosen_contour().name, "Shaft")
        self.assertTrue(self.window.centre.picture is not None)

    def test_dragging_the_slider_draws_the_newest_step_only(self):
        self.model.select(1)
        centre = self.window.centre
        centre.step_check.setChecked(True)
        APP.processEvents()
        drawn = []
        original = centre.redraw

        def counting():
            drawn.append(centre.step)
            original()

        with mock.patch.object(centre, "redraw", counting):
            first = centre.step
            for value in range(first + 3, first + 9):
                centre._slider.setValue(value)
            APP.processEvents()
        self.assertEqual(centre.step, first + 8)
        self.assertEqual(drawn[-1], first + 8)
        self.assertLessEqual(len(drawn), 3)  # not one draw for each of the six moves of the slider

    def test_stepping_works_out_the_materials_in_the_background_and_stops_with_it(self):
        self.model.select(1)
        centre = self.window.centre
        centre.step_check.setChecked(True)
        APP.processEvents()
        stepper = self.model.stepper()
        self.assertIs(centre._cached_stepper, stepper)
        self.assertTrue(stepper.wait_precompute(120))
        self.assertEqual(len(stepper._materials), stepper.count)
        centre.step_check.setChecked(False)
        APP.processEvents()
        self.assertIsNone(centre._cached_stepper)

    def test_the_window_closes_and_remembers_its_layout(self):
        with mock.patch.object(self.window, "_ask_save_changes", return_value=True):
            self.window.close()
        self.assertIsNotNone(self.model.app_settings.window_geometry)


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class DialogMemoryTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel
        from wop.ui.qt.dialog_memory import DialogMemory

        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "settings.json"
        self.model = AppModel(settings_path=self.path)
        self.memory = DialogMemory(self.model)
        APP.installEventFilter(self.memory)
        self.addCleanup(APP.removeEventFilter, self.memory)

    def test_a_dialog_opens_with_the_size_it_had_when_it_was_closed(self):
        from wop.ui.app_model import AppModel
        from wop.ui.qt.machines_dialog import MachinesDialog

        first = MachinesDialog(None, self.model)
        first.show()
        APP.processEvents()
        first.resize(first.width(), first.height() + 70)  # only the height: Qt keeps a restored width inside the (small, offscreen) screen
        size = (first.width(), first.height())
        first.accept()
        first.deleteLater()
        self.assertTrue(self.model.dialog_geometry("MachinesDialog"))
        restarted = AppModel(settings_path=self.path)  # the next run of the program
        APP.removeEventFilter(self.memory)
        self.memory = type(self.memory)(restarted)
        APP.installEventFilter(self.memory)
        second = MachinesDialog(None, restarted)
        self.addCleanup(second.deleteLater)
        second.show()
        APP.processEvents()
        self.assertEqual(second.height(), size[1])
        self.assertLessEqual(second.width(), size[0])  # never wider than it was; Qt makes it narrower when the screen is

    def test_a_dialog_of_qt_is_left_alone(self):
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox()
        self.addCleanup(box.deleteLater)
        box.show()
        APP.processEvents()
        box.close()
        self.assertEqual(self.model.dialog_geometry("QMessageBox"), "")


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class DialogsAndViewsTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel
        from wop.ui.qt.main_window import MainWindow

        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")
        self.model.open(ROOT / "examples" / "reference.wop.json")
        self.window = MainWindow(self.model)
        self.addCleanup(self.window.deleteLater)

    def test_every_dialog_and_view_can_be_built(self):
        from wop.core.lathe.workholding import JAWS_KIND
        from wop.ui.qt.centre_view import CentreView
        from wop.ui.qt.dialogs import ExportCheckDialog, ExportSelectedDialog, IssuesDialog
        from wop.ui.qt.machines_dialog import MachinesDialog
        from wop.ui.qt.materials_dialog import MaterialsDialog
        from wop.ui.qt.post_editor_dialog import PostEditorDialog
        from wop.ui.qt.preferences_dialog import FixedValuesDialog, PreferencesDialog
        from wop.ui.qt.sketch_dialog import SketchDialog
        from wop.ui.qt.tools_view import ToolsView
        from wop.ui.qt.view3d_dialog import View3DDialog
        from wop.ui.qt.workholding_view import WorkholdingView
        from wop.ui.app_model import ExportReport

        model, window = self.model, self.window
        machine = model.new_machine()
        model.use_machine(machine)
        number = model.program.tools[0].number
        jaws = model.add_workholding_item(JAWS_KIND)
        picture = "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>"
        for build in (
            lambda: MachinesDialog(window, model),
            lambda: MaterialsDialog(window, model),
            lambda: SketchDialog(window, target=model.tool_sketch_target(number)),
            lambda: SketchDialog(window, target=model.workholding_sketch_target(jaws)),
            lambda: SketchDialog(window, target=model.raw_part_sketch_target()),
            lambda: SketchDialog(window, target=model.path_sketch_target(model.add_block("custom_path"))),
            lambda: View3DDialog(window, model),
            lambda: PostEditorDialog(window, model, "linuxcnc"),
            lambda: PreferencesDialog(window, model),
            lambda: FixedValuesDialog(window, "text"),
            lambda: ExportCheckDialog(window, ExportReport(False, ("block 2 is left out",)), lambda: ExportReport(True)),
            lambda: ExportSelectedDialog(window, "title", lambda done: (picture, "notes", "code"), lambda done: None),
            lambda: IssuesDialog(window, []),
            lambda: ToolsView(model),
            lambda: WorkholdingView(model),
            lambda: CentreView(model),
        ):
            with self.subTest(build=build):
                dialog = build()
                dialog.deleteLater()

    def test_the_post_editor_pages_open(self):
        from wop.ui.qt.post_editor_dialog import PostEditorDialog

        dialog = PostEditorDialog(self.window, self.model, "linuxcnc")
        self.addCleanup(dialog.deleteLater)
        for row in range(dialog._pages.count()):
            dialog._pages.setCurrentRow(row)
            APP.processEvents()


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class ClickCommitTests(unittest.TestCase):
    def test_a_click_on_a_part_that_takes_no_focus_ends_the_editing(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

        from wop.ui.qt import click_commit
        from wop.ui.qt.number_boxes import NumberBox

        click_commit.install(APP)
        window = QWidget()
        layout = QVBoxLayout(window)
        box, label = NumberBox(), QLabel("a view")
        layout.addWidget(box)
        layout.addWidget(label)
        finished = []
        box.editingFinished.connect(lambda: finished.append(box.value()))
        window.show()
        window.activateWindow()
        QTest.qWaitForWindowActive(window)
        box.setFocus()
        APP.processEvents()
        self.assertTrue(box.hasFocus())
        box.lineEdit().setText("12")
        QTest.mouseClick(box.lineEdit(), Qt.LeftButton, Qt.NoModifier, QPoint(2, 2))  # in the field itself: stays
        APP.processEvents()
        self.assertEqual(finished, [])
        QTest.mouseClick(label, Qt.LeftButton)
        APP.processEvents()
        self.assertEqual(finished, [12.0])
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
