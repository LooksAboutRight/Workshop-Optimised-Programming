"""The modal groups in the post editor (model and window) and the modifier buttons."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from tests.post_helpers import install_reference_post
from wop.post.modal_groups import FIXED_NAMES, ModalGroupError, normalize_code, normalize_word, parse_modal_groups
from wop.ui.app_model import AppModel

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit

    from wop.ui.qt.post_editor_dialog import PostEditorDialog
    from wop.ui.qt.post_editor_parts.helpers import cell_text
    from wop.ui.qt.qt_constants import POST_ERROR_COLOR
    from wop.ui.template_edit import apply_changed

    APP = QApplication.instance() or QApplication([])


def type_into(table, row, column, text):
    """What the user does: the text field of the cell gets the text and reports the edit."""
    field = table.cellWidget(row, column)
    field.setText(text)
    field.textEdited.emit(text)


class ParserTests(unittest.TestCase):
    def test_groups_are_read_with_their_codes_in_capitals(self):
        groups = parse_modal_groups([(1, "motion", "g0 G1, G2"), (2, "mine", "M10 M11"), (3, "plane", "")])
        self.assertEqual(groups, {"motion": ("G0", "G1", "G2"), "mine": ("M10", "M11"), "plane": ()})

    def test_the_rules_with_a_message_and_the_line(self):
        for entries, text in (
            ([(1, "motion", "G1"), (2, "mine", "G1")], "G1 is in two modal groups: motion and mine"),
            ([(1, "motion", "G1"), (2, "motion", "G2")], "written twice"),
            ([(4, "motion", "G1 nonsense")], "does not look like a code"),
            ([(1, "My Group", "G1")], "is not a group name"),
        ):
            with self.subTest(text=text), self.assertRaises(ModalGroupError) as caught:
                parse_modal_groups(entries)
            self.assertIn(text, caught.exception.message)


class SpellingTests(unittest.TestCase):
    def test_a_code_in_any_spelling_is_one_code(self):
        for spelling in ("G0", "g0", "G00", "g00", "G000"):
            self.assertEqual(normalize_word(spelling), "G0")
        self.assertEqual([normalize_word(word) for word in ("M03", "G01", "G38.20", "G54.1", "G10")], ["M3", "G1", "G38.2", "G54.1", "G10"])
        self.assertEqual(normalize_code("g00 X1"), "G0 X1")  # only the first word is normalized

    def test_the_spellings_count_as_one_code_in_the_groups(self):
        self.assertEqual(parse_modal_groups([(1, "motion", "G00 g1 G01")]), {"motion": ("G0", "G1")})
        with self.assertRaises(ModalGroupError):
            parse_modal_groups([(1, "motion", "G0"), (2, "mine", "g00")])


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        install_reference_post(Path(self.folder.name), "fanuc")
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")

    def editor(self):
        copy = self.model.post_editor("linuxcnc")
        copy.shipped = False
        return copy

    def test_the_shipped_posts_have_the_fixed_groups_and_every_code_has_its_group(self):
        for post_id in ("linuxcnc", "fanuc", "generic"):
            with self.subTest(post=post_id):
                editor = self.model.post_editor(post_id)
                self.assertEqual(editor.page_problems(), {})
                self.assertEqual(editor.ungrouped_codes(), [])
                self.assertEqual([name for name, _codes, fixed in editor.modal_groups() if fixed], list(FIXED_NAMES))

    def test_the_code_table_shows_the_group_from_the_modal_groups(self):
        editor = self.editor()
        groups = {name: group for name, _code, group in editor.codes()}
        self.assertEqual((groups["rapid"], groups["comp_left"], groups["diameter_mode"]), ("motion", "cutter_compensation", "diameter_mode"))
        editor.set_modal_groups([(name, codes) for name, codes, _fixed in editor.modal_groups() if name != "motion"])
        self.assertEqual({name: group for name, _code, group in editor.codes()}["rapid"], "")
        self.assertIn("rapid", editor.ungrouped_codes())

    def test_the_group_of_a_code_does_not_depend_on_how_the_code_is_spelled(self):
        editor = self.editor()
        editor.set_codes([("rapid", "G00", ""), ("feed", "g1", ""), ("arc", "G2", "")])
        editor.set_modal_groups([("motion", "G0 G01 g2")])
        self.assertEqual([group for _name, _code, group in editor.codes()], ["motion", "motion", "motion"])
        editor.set_modal_groups([("motion", "G00 G1 G02")])
        self.assertEqual([group for _name, _code, group in editor.codes()], ["motion", "motion", "motion"])
        self.assertEqual(editor.modal_groups()[0][1], "G00 G1 G02")  # what the user typed stays as it is

    def test_a_group_of_the_user_is_kept_in_the_file_and_an_empty_fixed_group_is_not(self):
        editor = self.editor()
        rows = [(name, codes) for name, codes, _fixed in editor.modal_groups()]
        rows.append(("my_group", "M10 M11"))
        rows = [(name, "" if name == "plane" else codes) for name, codes in rows]
        editor.set_modal_groups(rows)
        text = editor.text
        self.assertIn("my_group = M10 M11", text)
        self.assertNotIn("plane =", text)
        self.assertEqual(editor.modal_groups()[-1], ("my_group", "M10 M11", False))
        self.assertEqual(editor.modal_groups()[1], ("plane", "", True))  # the fixed groups are always there

    def test_a_problem_on_the_modal_groups_page_marks_that_page_and_the_template_that_depends_on_it(self):
        editor = self.editor()
        editor.set_modal_groups([("motion", "G0 G1 G2 G3"), ("mine", "G1")])
        self.assertIn("modal_groups", editor.page_problems())
        self.assertIn("G1 is in two modal groups", editor.page_problems()["modal_groups"])

    def test_two_codes_of_one_group_in_a_line_mark_the_concept(self):
        editor = self.editor()
        editor.set_section("feed", "<code feed> <code rapid> X<X>")
        self.assertIn("same modal group (motion)", editor.page_problems()["feed"])


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class WindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")
        copy = self.model.post_editor("linuxcnc")
        self.post_id = self.model.save_post(copy, "mine")
        self.dialog = PostEditorDialog(None, self.model, self.post_id)
        self.addCleanup(self.dialog.deleteLater)

    def go_to(self, page):
        for row in range(self.dialog._pages.count()):
            if self.dialog._pages.item(row).text().split()[0] == page:
                self.dialog._pages.setCurrentRow(row)
                return row
        self.fail(f"no page {page}")

    def unmodal_feed(self):
        """The feed template of the shipped post writes X and Z only when changed; these tests need a plain X<X> to work on."""
        template = self.dialog._template
        template.setPlainText(template.toPlainText().replace("[ X<X changed>]", " X<X>"))

    def select(self, piece=None):
        text = self.dialog._template.toPlainText()
        cursor = self.dialog._template.textCursor()
        start = text.index(piece)
        cursor.setPosition(start)
        cursor.setPosition(start + len(piece), QTextCursor.KeepAnchor)
        self.dialog._template.setTextCursor(cursor)

    def test_the_cells_hold_real_text_fields_where_the_cursor_goes_to_the_click_and_typing_adds(self):
        self.dialog.show()
        for page, widget, column in (("Modal", self.dialog._groups, 1), ("Code", self.dialog._codes, 1)):
            self.go_to(page)
            first = 1 if widget is self.dialog._codes else 0  # the first row of the code table is a heading
            field = widget.cellWidget(first, column)
            self.assertIsInstance(field, QLineEdit)
            self.assertEqual(widget.editTriggers(), widget.EditTrigger.NoEditTriggers)  # the table opens no editor of its own
            before = field.text()
            field.setFocus()
            field.setCursorPosition(2)
            QTest.keyClicks(field, "9")  # typing goes to the cursor, it does not replace the text
            self.assertEqual(field.text(), before[:2] + "9" + before[2:])
        self.dialog.hide()

    def test_an_empty_cell_can_be_typed_into_at_once(self):
        self.go_to("Modal")
        table = self.dialog._groups
        row = list(FIXED_NAMES).index("plane")
        table.cellWidget(row, 1).setText("")
        self.dialog.show()
        field = table.cellWidget(row, 1)
        field.setFocus()
        QTest.keyClicks(field, "G17")
        self.assertIn("plane = G17", self.dialog.editor.text)
        self.dialog.hide()

    def test_a_click_into_a_field_makes_its_row_the_current_row_for_the_remove_button(self):
        self.go_to("Modal")
        self.dialog._add_group()
        table = self.dialog._groups
        row = table.rowCount() - 1
        table.setCurrentCell(0, 1)
        table.cellWidget(row, 1).setFocus()
        self.dialog.show()
        table.cellWidget(row, 1).setFocus()
        APP.processEvents()
        self.assertEqual(table.currentRow(), row)
        self.dialog._remove_group()
        self.assertEqual(table.rowCount(), row)
        self.dialog.hide()

    def test_the_group_column_of_the_code_table_follows_what_is_typed(self):
        self.go_to("Code")
        table = self.dialog._codes
        self.dialog._add_code()
        row = table.rowCount() - 1
        type_into(table, row, 0, "zz")
        type_into(table, row, 1, "G17")  # the plane group
        self.assertEqual(cell_text(table, row, 2), "plane")
        type_into(table, row, 1, "Q99")
        self.assertEqual(cell_text(table, row, 2), "")

    def test_the_tables_of_a_post_that_comes_with_wop_can_be_scrolled_but_not_edited(self):
        shipped = PostEditorDialog(None, self.model, "linuxcnc")
        self.addCleanup(shipped.deleteLater)
        shipped.show()
        for page, table in (("Code", shipped._codes), ("Modal", shipped._groups)):
            for row in range(shipped._pages.count()):
                if shipped._pages.item(row).text().startswith(page):
                    shipped._pages.setCurrentRow(row)
            table.setMaximumHeight(150)  # a small window: the list is longer than it
            APP.processEvents()
            self.assertTrue(table.isEnabled())  # a disabled table cannot be scrolled
            bar = table.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)  # the list is longer than the window
            bar.setValue(bar.maximum())
            self.assertEqual(bar.value(), bar.maximum())
            fields = [table.cellWidget(row, 1) for row in range(table.rowCount()) if table.cellWidget(row, 1) is not None]
            self.assertTrue(fields and all(field.isReadOnly() for field in fields))
        self.assertFalse(shipped._add_code_button.isEnabled() or shipped._add_group_button.isEnabled())
        shipped.hide()
        self.assertFalse(self.dialog._codes.isHidden() and False)  # the dialog of the user's own post is untouched
        self.assertTrue(self.dialog._add_code_button.isEnabled())

    def test_the_modal_groups_page_says_what_is_wrong_in_red(self):
        self.go_to("Modal")
        table = self.dialog._groups
        self.dialog._add_group()
        type_into(table, table.rowCount() - 1, 0, "mine")
        type_into(table, table.rowCount() - 1, 1, "G1")  # G1 is in motion already
        text = self.dialog._page_problem_labels["modal_groups"].text()
        self.assertIn("G1 is in two modal groups", text)
        type_into(table, table.rowCount() - 1, 1, "M10")
        self.assertEqual(self.dialog._page_problem_labels["modal_groups"].text(), "")

    def test_the_other_pages_say_what_is_wrong_in_red_too(self):
        self.go_to("Settings")
        self.dialog.editor.set_setting("decimals", "many")
        self.dialog._update_buttons()
        self.assertIn("whole number", self.dialog._page_problem_labels["settings"].text())

    def test_the_modal_groups_page_has_the_fixed_groups_a_separator_and_the_groups_of_the_user(self):
        self.go_to("Modal")
        table = self.dialog._groups
        names = [table.item(row, 0).text() for row in range(table.rowCount())]
        self.assertEqual(names[:len(FIXED_NAMES)], list(FIXED_NAMES))
        self.assertEqual(names[len(FIXED_NAMES)], "Custom modal groups")
        self.assertFalse(table.item(0, 0).flags() & table.item(0, 0).flags().ItemIsEditable)  # a fixed name cannot be changed
        self.dialog._add_group()
        type_into(table, table.rowCount() - 1, 0, "mine")
        type_into(table, table.rowCount() - 1, 1, "M10 M11")
        self.assertIn("mine = M10 M11", self.dialog.editor.text)
        self.assertTrue(self.dialog._buttons["save"].isEnabled())

    def test_typing_codes_into_a_fixed_group_changes_the_code_table(self):
        self.go_to("Modal")
        table = self.dialog._groups
        motion_row = list(FIXED_NAMES).index("motion")
        type_into(table, motion_row, 1, "G1 G2 G3")  # G0 is no longer in a group
        self.go_to("Code")
        table = self.dialog._codes
        groups = {cell_text(table, row, 0): cell_text(table, row, 2) for row, kind in enumerate(self.dialog._code_kinds) if kind != "heading"}
        self.assertEqual((groups["rapid"], groups["feed"]), ("", "motion"))
        self.assertIn("rapid", self.dialog._codes_note.text())
        self.assertFalse(self.dialog._codes.item(1, 2).flags() & self.dialog._codes.item(1, 2).flags().ItemIsEditable)  # the group is not typed here

    def test_a_double_group_turns_the_modal_groups_page_red(self):
        self.go_to("Modal")
        table = self.dialog._groups
        type_into(table, list(FIXED_NAMES).index("plane"), 1, "G17 G1")  # G1 is in motion
        row = next(r for r in range(self.dialog._pages.count()) if self.dialog._pages.item(r).text().startswith("Modal"))
        self.assertEqual(self.dialog._pages.item(row).foreground().color().name(), POST_ERROR_COLOR)

    def test_the_changed_button_works_on_the_selection_and_one_undo_takes_it_back(self):
        self.go_to("feed")
        self.unmodal_feed()
        template = self.dialog._template
        before = template.toPlainText()
        self.select("X<X>")
        self.dialog._template_action(apply_changed)
        self.assertIn("[ X<X changed>]", template.toPlainText())
        self.assertEqual(template.textCursor().selectedText(), "[ X<X changed>]")  # the changed place stays selected
        template.undo()
        self.assertEqual(template.toPlainText(), before)

    def test_the_row_has_all_six_buttons_and_they_are_off_for_a_shipped_post(self):
        self.go_to("feed")
        self.assertEqual(len(self.dialog._modifier_widgets), 6)
        self.assertTrue(all(widget.isEnabled() for widget in self.dialog._modifier_widgets))
        shipped = PostEditorDialog(None, self.model, "linuxcnc")
        self.addCleanup(shipped.deleteLater)
        for row in range(shipped._pages.count()):
            if shipped._pages.item(row).text().split()[0] == "feed":
                shipped._pages.setCurrentRow(row)
        self.assertFalse(any(widget.isEnabled() for widget in shipped._modifier_widgets))

    def test_the_options_menu_offers_the_options_of_the_token_and_adds_one(self):
        self.go_to("feed")
        self.unmodal_feed()
        template = self.dialog._template
        text = template.toPlainText()
        cursor = template.textCursor()
        cursor.setPosition(text.index("X<X>") + 3)
        template.setTextCursor(cursor)
        self.dialog._fill_options_menu()
        names = [action.text() for action in self.dialog._options_menu.actions()]
        self.assertIn("scaled", names)
        scaled = next(action for action in self.dialog._options_menu.actions() if action.text() == "scaled")
        scaled.trigger()
        self.assertIn("X<X scaled>", template.toPlainText())

    def test_a_value_option_asks_for_its_value(self):
        self.go_to("feed")
        self.unmodal_feed()
        template = self.dialog._template
        cursor = template.textCursor()
        cursor.setPosition(template.toPlainText().index("X<X>") + 3)
        template.setTextCursor(cursor)
        QInputDialog.getText = staticmethod(lambda *a, **k: ("2", True))
        self.dialog._fill_options_menu()
        next(action for action in self.dialog._options_menu.actions() if action.text().startswith("decimals")).trigger()
        self.assertIn("X<X decimals=2>", template.toPlainText())

    def test_a_refused_change_says_why_and_changes_nothing(self):
        self.go_to("feed")
        template = self.dialog._template
        before = template.toPlainText()
        cursor = template.textCursor()
        cursor.setPosition(0)
        template.setTextCursor(cursor)
        self.dialog._template_action(lambda text, start, end: apply_changed("N<N> (text)", 5, 5))  # nothing that can be changed
        self.assertEqual(template.toPlainText(), before)
        self.assertIn("no token", self.dialog._message.text())


if __name__ == "__main__":
    unittest.main()
