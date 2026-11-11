"""Posts with problems: saved, opened in the editor, marked, not used; unreadable files (design of 2026-10-19)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from wop.ui.app_model import AppModel, ModelError

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from wop.ui.qt.post_editor_dialog import PostEditorDialog
    from wop.ui.qt.qt_constants import POST_ERROR_COLOR, POST_ERROR_LINE_TEXT_COLOR

    APP = QApplication.instance() or QApplication([])


class ModelCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")

    def posts_folder(self):
        return self.model.posts_folder_path()

    def save_with_problem(self, name="Half done"):
        editor = self.model.post_editor("linuxcnc")
        editor.set_section("feed", "G1 <Y>")
        return self.model.save_post(editor, self.model.unique_post_id(name))

    def write_unreadable(self, post_id="binary"):
        (self.posts_folder() / f"{post_id}.post.ini").write_bytes(bytes([255, 254, 0, 1]))
        self.model.reload_posts()


class LibraryTests(ModelCase):
    def test_a_post_with_a_problem_is_saved_and_found_again_as_unfinished(self):
        post_id = self.save_with_problem()
        self.assertTrue((self.posts_folder() / f"{post_id}.post.ini").exists())
        library = self.model.post_library
        self.assertNotIn(post_id, library.posts)
        self.assertIn(post_id, library.unfinished)
        self.assertIn("unknown token", library.unfinished[post_id].problem)
        self.assertEqual(library.unfinished[post_id].name, "LinuxCNC")  # the name of the file, not the id

    def test_the_machine_offers_only_posts_without_problems_the_editor_offers_all(self):
        problem_id, = (self.save_with_problem(),)
        self.write_unreadable()
        self.assertNotIn(problem_id, dict(self.model.post_choices()))
        self.assertNotIn("binary", dict(self.model.post_choices()))
        entries = {post_id: state for post_id, _name, state in self.model.post_editor_choices()}
        self.assertEqual((entries["linuxcnc"], entries[problem_id], entries["binary"]), ("", "problems", "unreadable"))
        states = [state for _id, _name, state in self.model.post_editor_choices()]
        self.assertEqual(states, sorted(states, key=lambda state: ("", "problems", "unreadable").index(state)))  # the usable ones first

    def test_a_machine_with_such_a_post_gets_the_default_post_and_a_message_that_says_why(self):
        problem_id = self.save_with_problem()
        self.write_unreadable()
        library = self.model.post_library
        definition, message = library.choose(problem_id)
        self.assertEqual(definition.post_id, "linuxcnc")
        self.assertIn("has problems and is not used", message)
        self.assertNotIn("not found", message)
        self.assertIn("cannot be read and is not used", library.choose("binary")[1])
        self.assertIn("was not found", library.choose("nothing")[1])

    def test_a_file_with_a_shipped_name_is_still_not_used(self):
        (self.posts_folder() / "linuxcnc.post.ini").write_text("nonsense", encoding="utf-8")
        self.model.reload_posts()
        self.assertNotIn("linuxcnc", self.model.post_library.unfinished)
        self.assertTrue(any("shipped post has this name" in text for text in self.model.post_library.problems))

    def test_fixing_the_post_makes_it_usable_again(self):
        post_id = self.save_with_problem()
        editor = self.model.post_editor(post_id)
        self.assertTrue(editor.page_problems())
        editor.set_section("feed", "G1 X<X>")
        self.model.save_post(editor)
        self.assertIn(post_id, self.model.post_library.posts)
        self.assertNotIn(post_id, self.model.post_library.unfinished)

    def test_posts_with_problems_and_unreadable_files_can_be_deleted(self):
        problem_id = self.save_with_problem()
        self.write_unreadable()
        self.model.delete_post(problem_id)
        self.model.delete_post("binary")
        self.assertEqual(self.model.post_library.unfinished, {})
        self.assertEqual(self.model.post_library.unreadable, {})

    def test_an_unreadable_file_opens_as_a_read_only_placeholder(self):
        self.write_unreadable()
        editor = self.model.post_editor("binary")
        self.assertTrue(editor.shipped and editor.unreadable)
        with self.assertRaises(ModelError):
            self.model.save_post(editor, "binary")

    def test_the_id_of_a_new_post_is_not_taken_by_a_file_with_problems(self):
        problem_id = self.save_with_problem("Half done")
        self.assertEqual(problem_id, "half_done")
        self.assertEqual(self.model.unique_post_id("Half done"), "half_done_2")


class PageProblemTests(ModelCase):
    def editor(self):
        return self.model.post_editor("linuxcnc")

    def test_a_good_post_has_no_problem_pages(self):
        self.assertEqual(self.editor().page_problems(), {})

    def test_a_template_problem_marks_its_concept_only(self):
        editor = self.editor()
        editor.set_section("feed", "G1 <Y>")
        problems = editor.page_problems()
        self.assertEqual(list(problems), ["feed"])
        self.assertIn("unknown token", problems["feed"])

    def test_each_kind_of_page_is_marked(self):
        editor = self.editor()
        editor.set_setting("decimals", "many")
        editor.set_codes([("rapid", "", "")])
        editor.set_meta("format_version", "99")
        problems = editor.page_problems()
        for page in ("post", "settings", "codes"):
            self.assertIn(page, problems)

    def test_an_unknown_section_marks_the_post_page(self):
        editor = self.editor()
        editor.set_section("nonsense", "x")
        self.assertIn("post", editor.page_problems())

    def test_a_line_that_belongs_to_no_page_still_marks_a_page(self):
        editor = self.editor()
        editor._text.preamble = ["text before the first section"]
        self.assertIn("post", editor.page_problems())


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class DialogTests(ModelCase):
    def dialog(self, start):
        dialog = PostEditorDialog(None, self.model, start)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_dropdown_marks_and_separates_the_posts_that_cannot_be_used(self):
        problem_id = self.save_with_problem()
        self.write_unreadable()
        dialog = self.dialog("linuxcnc")
        texts = [dialog._posts.itemText(i) for i in range(dialog._posts.count())]
        self.assertTrue(any(text.endswith("(has problems)") for text in texts))
        self.assertTrue(any(text.endswith("(unreadable file)") for text in texts))
        self.assertIn("", texts)  # the separator between the usable posts and the rest
        self.assertLess(texts.index(""), min(i for i, text in enumerate(texts) if "(has problems)" in text))
        self.assertNotEqual(dialog._posts.findData(problem_id), -1)

    def test_a_post_with_problems_opens_normally_and_its_pages_are_red(self):
        problem_id = self.save_with_problem()
        dialog = self.dialog(problem_id)
        self.assertEqual(dialog.editor.post_id, problem_id)
        red = {dialog._pages.item(row).text().split()[0] for row in range(dialog._pages.count())
               if dialog._pages.item(row).foreground().color().name() == POST_ERROR_COLOR}
        self.assertEqual(red, {"feed"})
        self.assertIn("unknown token", dialog._pages.item(
            next(row for row in range(dialog._pages.count()) if dialog._pages.item(row).text().split()[0] == "feed")).toolTip())

    def test_typing_a_mistake_turns_the_page_red_and_fixing_it_turns_it_back(self):
        QApplication.processEvents()
        dialog = self.dialog("linuxcnc")
        editor = dialog.editor
        editor.shipped = False  # as in a copy
        dialog._page = "feed"
        dialog._fill_page()
        dialog._template.setPlainText("G1 <Y>")
        dialog._template_edited()
        feed_row = next(row for row in range(dialog._pages.count()) if dialog._pages.item(row).text().split()[0] == "feed")
        self.assertEqual(dialog._pages.item(feed_row).foreground().color().name(), POST_ERROR_COLOR)
        dialog._template.setPlainText("G1 X<X>")
        dialog._template_edited()
        self.assertNotEqual(dialog._pages.item(feed_row).foreground().color().name(), POST_ERROR_COLOR)

    def test_the_line_with_the_problem_has_dark_text_on_its_light_background(self):
        problem_id = self.save_with_problem()
        dialog = self.dialog(problem_id)
        dialog._page = "feed"
        dialog._fill_page()
        selections = dialog._template.extraSelections()
        self.assertTrue(selections)
        self.assertEqual(selections[0].format.foreground().color().name(), POST_ERROR_LINE_TEXT_COLOR)

    def test_an_unreadable_file_can_only_be_deleted(self):
        self.write_unreadable()
        dialog = self.dialog("binary")
        self.assertTrue(dialog.editor.unreadable)
        self.assertTrue(dialog._buttons["delete"].isEnabled())
        for key in ("save", "copy"):
            self.assertFalse(dialog._buttons[key].isEnabled())
        self.assertIn("cannot be read", dialog._file_note.text())


if __name__ == "__main__":
    unittest.main()
