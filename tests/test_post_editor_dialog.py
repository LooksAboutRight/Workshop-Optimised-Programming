"""The post editor window with the real PySide6 (offscreen, no screen needed). Skipped when PySide6 is not installed or is the stand-in."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

    from wop.post.base import Feature
    from wop.post.post_definition import parse_post
    from wop.ui.app_model import AppModel
    from wop.ui.qt.post_editor_dialog import PostEditorDialog

    APP = QApplication.instance() or QApplication([])


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class PostEditorDialogTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")
        self.dialog = PostEditorDialog(None, self.model, "linuxcnc")
        self.addCleanup(self.dialog.deleteLater)

    def go_to(self, page):
        for row in range(self.dialog._pages.count()):
            if self.dialog._pages.item(row).text().split()[0] == page:
                self.dialog._pages.setCurrentRow(row)
                return
        self.fail(f"no page {page}")

    def test_every_page_opens(self):
        for row in range(self.dialog._pages.count()):
            self.dialog._pages.setCurrentRow(row)
            APP.processEvents()
        self.assertEqual(self.dialog._page, "note_entry")

    def test_a_shipped_post_is_read_only_and_a_copy_is_not(self):
        self.go_to("feed")
        self.assertTrue(self.dialog._template.isReadOnly())
        self.assertFalse(self.dialog._buttons["save"].isEnabled())
        QInputDialog.getText = staticmethod(lambda *a, **k: ("My Lathe", True))
        self.dialog._save_as()
        self.assertEqual(self.dialog.editor.post_id, "my_lathe")
        self.go_to("feed")
        self.assertFalse(self.dialog._template.isReadOnly())
        self.assertTrue((Path(self.folder.name) / "posts" / "my_lathe.post.ini").exists())

    def test_typing_changes_the_sample_output_and_a_mistake_shows_where(self):
        QInputDialog.getText = staticmethod(lambda *a, **k: ("Mine", True))
        self.dialog._save_as()
        self.go_to("feed")
        self.dialog._template.setPlainText("G1 X<X> Z<Z> [F<F changed>]")
        self.dialog._template_edited()
        self.assertEqual(self.dialog._present.toPlainText(), "G1 X25 Z-3 F0.2")
        self.assertEqual(self.dialog._absent.toPlainText(), "G1 X25 Z-3")
        self.dialog._x_mode.setCurrentIndex(1)
        self.assertEqual(self.dialog._present.toPlainText(), "G1 X12.5 Z-3 F0.2")
        self.dialog._template.setPlainText("G1 X<X>\nG1 <Y>")
        self.dialog._template_edited()
        self.assertIn("unknown token <Y>", self.dialog._problem.text())
        self.assertIn("line 2", self.dialog._problem.text())
        self.assertEqual(len(self.dialog._template.extraSelections()), 1)
        self.assertTrue(self.dialog.editor.dirty)
        self.assertIn("*", self.dialog.windowTitle())

    def test_the_token_grid_puts_a_token_into_the_template(self):
        QInputDialog.getText = staticmethod(lambda *a, **k: ("Mine", True))
        self.dialog._save_as()
        self.go_to("rapid")
        self.dialog._template.setPlainText("")
        self.dialog._insert("<X>")
        self.assertEqual(self.dialog._template.toPlainText(), "<X>")
        self.assertGreater(self.dialog._tokens.count(), 1)

    def test_settings_and_code_pages_change_the_post_and_the_features_follow(self):
        QInputDialog.getText = staticmethod(lambda *a, **k: ("Mine", True))
        self.dialog._save_as()
        self.go_to("Settings")
        self.dialog._setting_widgets["decimals"].setValue(2)
        self.assertEqual(self.dialog.editor.settings().decimals, 2)
        self.go_to("Code")
        self.dialog._add_code()
        for column, text in ((0, "zz"), (1, "G99")):
            field = self.dialog._codes.cellWidget(self.dialog._codes.rowCount() - 1, column)
            field.setText(text)
            field.textEdited.emit(text)
        self.assertEqual(self.dialog.editor.codes()[-1][:2], ("zz", "G99"))
        self.go_to("Settings")
        self.assertTrue(self.dialog._setting_widgets["x_diameters"].isChecked())
        self.dialog._setting_widgets["x_diameters"].setChecked(False)  # a feature follows a setting: there is no Features page any more
        self.assertFalse(self.dialog.editor.settings().x_diameters)
        self.assertNotIn(Feature.DIAMETER_MODE, parse_post(self.dialog.editor.text, "x").features)
        self.assertFalse(any(self.dialog._pages.item(row).text() == "Features" for row in range(self.dialog._pages.count())))

    def test_the_work_offsets_are_added_numbered_and_removed(self):
        QInputDialog.getText = staticmethod(lambda *a, **k: ("Mine", True))
        self.dialog._save_as()
        self.go_to("Code")
        self.assertEqual(len(self.dialog.editor.work_offset_rows()), 9)
        self.dialog._add_offset()
        row = self.dialog._code_kinds.index("offset") + 9  # right after the ninth offset
        self.assertEqual(self.dialog._code_kinds[row], "offset")
        self.assertEqual(self.dialog._codes.item(row, 0).text(), "work_offset_10")
        field = self.dialog._codes.cellWidget(row, 1)
        field.setText("G54.1 P1")
        field.textEdited.emit("G54.1 P1")
        self.assertEqual(self.dialog.editor.work_offset_rows()[-1][:2], ("work_offset_10", "G54.1 P1"))
        self.dialog._codes.setCurrentCell(self.dialog._code_kinds.index("offset"), 0)  # remove the first one
        self.dialog._remove_code()
        names = [name for name, _code, _group in self.dialog.editor.work_offset_rows()]
        self.assertEqual(names, [f"work_offset_{number}" for number in range(1, 10)])  # numbered again, in the order of the rows
        self.assertEqual(self.dialog.editor.work_offset_rows()[0][1], "G55")
        self.assertEqual(self.dialog.editor.work_offset_rows()[-1][1], "G54.1 P1")

    def test_new_save_and_delete(self):
        self.dialog._new()
        self.assertEqual(self.dialog.editor.post_id, "")
        QInputDialog.getText = staticmethod(lambda *a, **k: ("Brand new", True))
        self.dialog._save()
        self.assertEqual(self.dialog.editor.post_id, "brand_new")
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        self.dialog._delete()
        self.assertNotIn("brand_new", self.model.post_library.posts)


if __name__ == "__main__":
    unittest.main()
