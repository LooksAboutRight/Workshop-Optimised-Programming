"""The toolbox parts of the window with the real PySide6, offscreen: the empty Tools view, the toolbox dialog, the Use toolbox menu
and the question before a toolbox replaces the tools of a project (T17 to T19)."""

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
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    APP = QApplication.instance() or QApplication([])

from wop.core.constants import NO_TOOL_NUMBER
from wop.core.tooling.toolbox import Toolbox, ToolboxEntry
from wop.ui.model import helpers

ENTRY = ToolboxEntry


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class ToolboxWindowTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel
        from wop.ui.qt.main_window import MainWindow

        was = helpers.NEW_PROJECT_USES_STUB_TOOLS
        helpers.NEW_PROJECT_USES_STUB_TOOLS = False  # a real new project: no tools
        self.addCleanup(setattr, helpers, "NEW_PROJECT_USES_STUB_TOOLS", was)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.model = AppModel(settings_path=Path(folder.name) / "settings.json")
        self.names = [t.name for t in self.model.tool_library]
        self.window = MainWindow(self.model)
        self.addCleanup(self.window.deleteLater)
        self.window.show()

    def test_an_empty_tools_view_shows_one_grey_line_that_is_not_a_tool(self):
        self.model.show_tools()
        APP.processEvents()
        view = self.window.centre.tools_view
        self.assertEqual(view.tools.count(), 1)
        item = view.tools.item(0)
        self.assertIn("No tools yet", item.text())
        self.assertEqual(item.flags(), Qt.NoItemFlags)
        self.assertIsNone(self.model.selected_tool)

    def test_the_tools_view_says_which_toolbox_and_can_make_it_the_default(self):
        view = self.window.centre.tools_view
        self.model.show_tools()
        APP.processEvents()
        self.assertEqual(view.toolbox_line.text(), "Toolbox: none")
        self.assertFalse(view.make_default.isEnabled())
        self.model.save_toolbox(Toolbox("Box", (ENTRY(self.names[0], 1),)))
        self.model.apply_toolbox("Box")
        APP.processEvents()
        self.assertEqual(view.toolbox_line.text(), "Toolbox: Box")
        self.assertTrue(view.make_default.isEnabled())
        view.make_default.click()
        self.assertEqual(self.model.default_toolbox, "Box")
        self.assertEqual(view.toolbox_line.text(), "Toolbox: Box (default)")
        self.assertFalse(view.make_default.isEnabled())

    def test_save_as_toolbox_asks_whether_to_update_the_current_one(self):
        from PySide6.QtWidgets import QMessageBox as Box

        view = self.window.centre.tools_view
        self.model.save_toolbox(Toolbox("Box", (ENTRY(self.names[0], 1),)))
        self.model.apply_toolbox("Box")
        self.model.add_tool_from_library(self.names[1])

        def answer(which):
            def exec_(box):
                texts = {"update": "Update", "new": "Make a new"}
                box._chosen = next((b for b in box.buttons() if which in texts and b.text().startswith(texts[which])), None)
                return 0
            return exec_

        with mock.patch.object(Box, "exec", answer("update")), mock.patch.object(Box, "clickedButton", lambda box: box._chosen):
            view._save_as_toolbox()
        self.assertEqual([b.name for b in self.model.toolboxes], ["Box"])
        self.assertEqual(len(self.model.toolboxes[0].entries), 2)
        self.model.add_tool_from_library(self.names[2])
        with mock.patch.object(Box, "exec", answer("new")), mock.patch.object(Box, "clickedButton", lambda box: box._chosen),                 mock.patch("wop.ui.qt.tools_view.QInputDialog.getText", return_value=("Job", True)):
            view._save_as_toolbox()
        self.assertEqual(sorted(b.name for b in self.model.toolboxes), ["Box", "Job"])
        self.assertEqual(len(self.model.toolboxes[0].entries) + len(self.model.toolboxes[1].entries), 5)
        before = self.model.toolboxes
        with mock.patch.object(Box, "exec", answer("cancel")), mock.patch.object(Box, "clickedButton", lambda box: box._chosen):
            view._save_as_toolbox()
        self.assertEqual(self.model.toolboxes, before)

    def test_the_tools_view_follows_the_tool_numbers(self):
        self.model.save_toolbox(Toolbox("Box", (ENTRY(self.names[0], 7), ENTRY(self.names[1], 2), ENTRY(self.names[2], 4))))
        self.model.apply_toolbox("Box")
        self.model.show_tools()
        APP.processEvents()
        view = self.window.centre.tools_view
        self.assertEqual([view.tools.item(r).text()[:3].strip() for r in range(view.tools.count())], ["T2", "T4", "T7"])
        self.assertEqual(self.model.selected_tool, 2)
        view.tools.setCurrentRow(2)
        self.assertEqual(self.model.selected_tool, 7)

    def test_the_dialog_makes_a_box_and_refuses_a_number_used_twice(self):
        from wop.ui.qt.toolboxes_dialog import ToolboxesDialog

        with mock.patch("wop.ui.qt.toolboxes_dialog.QInputDialog.getText", return_value=("Standard", True)):
            dialog = ToolboxesDialog(self.window, self.model)
            dialog._new()
        self.assertEqual([b.name for b in self.model.toolboxes], ["Standard"])
        dialog._add_row()
        dialog._add_row()
        self.assertEqual([(e.tool_name, e.number) for e in self.model.toolboxes[0].entries], [(self.names[0], 1), (self.names[1], 2)])
        dialog._table.cellWidget(1, 1).setValue(1)  # the same number as the first tool
        self.assertIn("Not saved", dialog._message.text())
        self.assertEqual([e.number for e in self.model.toolboxes[0].entries], [1, 2])
        dialog._table.cellWidget(1, 1).setValue(5)
        dialog._table.cellWidget(1, 2).setValue(3)
        self.assertEqual([(e.number, e.offset_number) for e in self.model.toolboxes[0].entries], [(1, None), (5, 3)])
        dialog._toggle_default()
        self.assertEqual(self.model.default_toolbox, "Standard")
        dialog._table.setCurrentCell(0, 0)
        dialog._remove_row()
        self.assertEqual([e.number for e in self.model.toolboxes[0].entries], [5])
        dialog._toggle_default()
        self.assertIsNone(self.model.default_toolbox)

    def test_the_use_toolbox_menu_lists_the_boxes(self):
        from PySide6.QtWidgets import QMenu

        self.model.save_toolbox(Toolbox("Standard", (ENTRY(self.names[0], 1),)))
        self.model.set_default_toolbox("Standard")
        menu = QMenu()
        self.window._fill_toolbox_menu(menu)
        self.assertEqual([a.text() for a in menu.actions()], ["Standard (default)"])
        menu.actions()[0].trigger()
        self.assertEqual([t.number for t in self.model.program.tools], [1])

    def test_the_question_names_the_blocks_that_lose_their_tool(self):
        self.model.save_toolbox(Toolbox("A", (ENTRY(self.names[0], 1), ENTRY(self.names[1], 2))))
        self.model.save_toolbox(Toolbox("B", (ENTRY(self.names[1], 1),)))
        self.model.apply_toolbox("A")
        self.model.add_block("facing")
        self.model.add_block("turning")
        self.model.replace_block(1, replace(self.model.blocks[1], tool_number=2))
        with mock.patch("wop.ui.qt.window_parts.actions.QMessageBox.question", return_value=QMessageBox.No) as ask:
            self.window._use_toolbox("B")
        text = ask.call_args.args[2]
        self.assertIn("Block 1", text)
        self.assertIn("no tool chosen", text)
        self.assertIn("Block 2", text)
        self.assertEqual([b.tool_number for b in self.model.blocks], [1, 2])  # No: nothing changed
        with mock.patch("wop.ui.qt.window_parts.actions.QMessageBox.question", return_value=QMessageBox.Yes):
            self.window._use_toolbox("B")
        self.assertEqual([b.tool_number for b in self.model.blocks], [NO_TOOL_NUMBER, 1])

    def test_no_question_when_no_block_changes(self):
        self.model.save_toolbox(Toolbox("A", (ENTRY(self.names[0], 1),)))
        with mock.patch("wop.ui.qt.window_parts.actions.QMessageBox.question") as ask:
            self.window._use_toolbox("A")
        ask.assert_not_called()
        self.assertEqual([t.number for t in self.model.program.tools], [1])

    def test_the_project_tools_become_a_toolbox_when_they_are_in_the_library(self):
        number = self.model.add_tool_from_library(self.names[0])
        self.model.save_project_tools_as_toolbox("Mine")
        self.assertEqual([(e.tool_name, e.number) for e in self.model.toolboxes[0].entries], [(self.names[0], number)])
        self.model.add_tool_of_type("turning")  # made in the project: not in the library
        with self.assertRaises(Exception):
            self.model.save_project_tools_as_toolbox("Other")


if __name__ == "__main__":
    unittest.main()
