"""Smoke tests of the Qt code with a stand-in for PySide6 (only runs when PySide6 is not installed).

The stand-in (tools/sandbox_standin/fake_pyside6.py) accepts every Qt call, so these tests find wrong names, wrong
arguments to our own code, broken signal wiring and exceptions in the window code. They say nothing about how the
window looks. With the real PySide6 installed they are skipped (the program itself is the test then).
"""

import importlib
import pkgutil
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent / "tools" / "sandbox_standin"
sys.path.insert(0, str(HERE))

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False



def fake_qt():
    import fake_pyside6

    fake_pyside6.install()


@unittest.skipIf(HAVE_REAL_QT, "the real PySide6 is installed")
class QtImportTests(unittest.TestCase):
    def test_every_qt_module_imports(self):
        fake_qt()
        import wop.ui.qt as package

        for info in pkgutil.iter_modules(package.__path__):
            with self.subTest(module=info.name):
                importlib.import_module(f"wop.ui.qt.{info.name}")


@unittest.skipIf(HAVE_REAL_QT, "the real PySide6 is installed")
class WindowTests(unittest.TestCase):
    def setUp(self):
        fake_qt()
        from wop.ui.app_model import AppModel
        from wop.ui.qt.main_window import MainWindow

        self.model = AppModel()
        self.model.auto_check = False  # the stand-in region is slow
        self.window = MainWindow(self.model)

    def test_the_window_shows_every_block_type(self):
        from wop.core.blocks import BLOCK_TYPES

        for type_name in BLOCK_TYPES.names():
            with self.subTest(block=type_name):
                index = self.model.add_block(type_name)
                self.model.select(index)

    def test_a_thread_designation_typed_in_the_form_shows_its_values_at_once(self):
        from wop.ui.block_forms import form_for
        from wop.ui.qt import main_window

        index = self.model.add_block("threading")
        self.model.select(index)
        shown = []
        self.window._show_form = lambda: shown.append(True)  # what the timer would call
        main_window.QTimer.singleShot = staticmethod(lambda _ms, call: call())
        block = self.model.blocks[index]
        spec = [s for s in form_for(block, self.model.form_context()) if s.path == ("designation",)][0]
        self.window._value_edited(spec, "M10x1.5")
        self.assertEqual(self.model.blocks[index].pitch_mm, 1.5)
        self.assertTrue(shown)

    def test_the_machine_settings_button_of_the_setup_form_opens_the_machines_dialog(self):
        from wop.ui.block_forms import FieldKind, form_for
        from wop.ui.qt import main_window

        opened = []
        from wop.ui.qt.window_parts import actions

        actions.MachinesDialog = lambda parent, model: type("Dialog", (), {"exec": lambda self: opened.append(model)})()
        main_window.QTimer.singleShot = staticmethod(lambda _ms, call: call())
        button = next(s for s in form_for(self.model.setup_form()) if s.kind is FieldKind.BUTTON)
        self.window._form_action(button)
        self.assertEqual(opened, [self.model])

    def test_the_setup_tools_workholding_and_toolholding_views_show(self):
        self.model.show_tools()
        self.model.show_workholding()
        self.model.show_toolholding()
        self.model.select(None)

    def test_the_contour_panel_shows_the_contour_and_renames_it(self):
        from wop.ui.qt import contour_panel

        contour_id = self.model.new_contour()
        panel = contour_panel.ContourPanel(self.model)
        panel.show_contour()
        panel._name.setText("Shaft")
        panel._name_changed()
        self.assertEqual(self.model.selected_contour, contour_id)
        self.assertEqual(self.model.chosen_contour().name, "Shaft")

    def test_every_dialog_and_view_can_be_built(self):
        from wop.core.lathe.workholding import JAWS_KIND
        from wop.ui.qt.machines_dialog import MachinesDialog
        from wop.ui.qt.materials_dialog import MaterialsDialog
        from wop.ui.qt.tools_view import ToolsView
        from wop.ui.qt.view3d_dialog import View3DDialog
        from wop.ui.qt.workholding_view import WorkholdingView
        from wop.ui.qt.toolholding_view import ToolholdingView
        from wop.ui.qt.centre_view import CentreView

        model = self.model
        name = model.new_machine()
        model.use_machine(name)
        number = model.program.tools[0].number
        item = model.add_workholding_item(JAWS_KIND)
        for build in (
            lambda: MachinesDialog(self.window, model),
            lambda: MaterialsDialog(self.window, model),
            lambda: View3DDialog(self.window, model),
            lambda: ToolsView(model),
            lambda: WorkholdingView(model),
            lambda: ToolholdingView(model),
            lambda: CentreView(model),
        ):
            with self.subTest(build=build):
                build()


def event(**answers):
    """A Qt event with the answers our handlers ask for."""
    from types import SimpleNamespace

    return SimpleNamespace(accept=lambda: None, ignore=lambda: None, **answers)


@unittest.skipIf(HAVE_REAL_QT, "the real PySide6 is installed")
class ZoomAndPanTests(unittest.TestCase):
    def test_wheel_drag_and_double_click_change_and_reset_the_view(self):
        fake_qt()
        from types import SimpleNamespace

        from wop.ui.qt.overlay_svg import OverlaySvgWidget
        from PySide6.QtCore import Qt

        class Sized(OverlaySvgWidget):
            def width(self): return 400
            def height(self): return 300
            def renderer(self): return SimpleNamespace(defaultSize=lambda: SimpleNamespace(width=lambda: 200, height=lambda: 100),
                                                       setAspectRatioMode=lambda *_: None, render=lambda *_: None)
            def update(self): pass

        widget = Sized()
        at = lambda x, y: SimpleNamespace(x=lambda: x, y=lambda: y)  # noqa: E731
        before = widget._view.view_rect(widget._base_rect())
        widget.wheelEvent(event(angleDelta=lambda: SimpleNamespace(y=lambda: 120), position=lambda: at(100.0, 80.0)))
        zoomed = widget._view.view_rect(widget._base_rect())
        self.assertNotEqual(before, zoomed)
        widget.mousePressEvent(event(button=lambda: Qt.LeftButton, position=lambda: at(10.0, 10.0)))
        widget.mouseMoveEvent(event(position=lambda: at(30.0, 25.0)))
        widget.mouseReleaseEvent(event())
        self.assertNotEqual(widget._view.view_rect(widget._base_rect()), zoomed)
        widget.mouseDoubleClickEvent(event())
        self.assertEqual(widget._view.view_rect(widget._base_rect()), before)


@unittest.skipIf(HAVE_REAL_QT, "the real PySide6 is installed")
class WindowLifeTests(unittest.TestCase):
    def setUp(self):
        fake_qt()
        from wop.ui.app_model import AppModel
        from wop.ui.qt.main_window import MainWindow

        self.model = AppModel()
        self.model.auto_check = False
        self.window = MainWindow(self.model)

    def test_closing_remembers_the_layout(self):
        from wop.ui.qt import main_window

        with mock.patch.object(self.window, "_ask_save_changes", return_value=True):
            self.window.closeEvent(event())
        self.assertTrue(self.model.app_settings.window_geometry is not None)

    def test_the_last_folder_is_remembered_and_used_as_the_start_of_a_dialog(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            name = str(Path(folder) / "part.wop.json")
            self.assertEqual(self.window._chosen(name), name)
            self.assertEqual(self.window._dialog_start("x.json"), str(Path(folder) / "x.json"))
        self.assertEqual(self.window._chosen(""), "")

    def test_activating_the_window_looks_for_changed_files(self):
        from PySide6.QtWidgets import QMainWindow
        from PySide6.QtCore import QEvent

        with mock.patch.object(self.model, "reload_changed_files", return_value="Libraries were reloaded.") as reload, \
             mock.patch.object(self.window, "_say") as say:
            self.window.event(event(type=lambda: QEvent.WindowActivate))
        reload.assert_called_once()
        say.assert_called_once_with("Libraries were reloaded.")

    def test_the_library_question_lists_new_tools(self):
        from wop.ui.qt import main_window

        with mock.patch.object(self.model, "tools_new_to_library", return_value=[1]), \
             mock.patch.object(self.model, "tools_differing_from_library", return_value=[]):
            self.window._ask_update_tool_library()


if __name__ == "__main__":
    unittest.main()
