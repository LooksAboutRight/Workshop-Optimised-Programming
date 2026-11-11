"""Custom concepts (functions) of a post file and their variables: reading, writing, the editor, the sample post."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from wop.post.engine import TemplatePost
from wop.post.post_definition import PostFileError, parse_post
from wop.post.samples import render_sample
from wop.post.variables import VariableError, check_values, parse_variables, read_functions, sample_values
from wop.ui.app_model import AppModel

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

    from wop.ui.qt.post_editor_dialog import PostEditorDialog
    from wop.ui.qt.qt_constants import POST_ERROR_COLOR

    APP = QApplication.instance() or QApplication([])

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "posts" / "linuxcnc_custom_function.post.ini"
HEAD = "[post]\nname = x\nformat_version = 1\n[codes]\nopen = M100\nmove = M101\nclose = M102\n"


def post(extra):
    return parse_post(HEAD + extra, "x")


def declared(*lines):
    return parse_variables([(number, *line.split(" = ", 1)) for number, line in enumerate(lines, start=1)])


class VariableTests(unittest.TestCase):
    def test_every_type_and_every_key(self):
        found = declared('length = float min=0 max=500 default=10 unit=mm label="Feed distance"', "count = int default=3", "turns = uint", "air = bool default=yes", "text = string default=hello")
        self.assertEqual([v.type for v in found], ["float", "int", "uint", "bool", "string"])
        length = found[0]
        self.assertEqual((length.minimum, length.maximum, length.default, length.unit, length.label), (0, 500, 10, "mm", "Feed distance"))
        self.assertEqual((found[1].default, found[2].default, found[2].minimum), (3, 0, 0))  # a uint starts at 0
        self.assertEqual((found[3].default, found[4].default), (True, "hello"))

    def test_the_label_is_the_name_made_readable_and_the_prefix_user_is_not_needed(self):
        self.assertEqual(declared("feed_distance = float")[0].label, "Feed distance")

    def test_the_rules_each_with_a_message(self):
        for line, text in (
            ("tool = float", "start of the token <tool"),
            ("X = float", "is not a variable name"),
            ("code = float", "is a token of the program"),
            ("length = float\nlength = int", "declared twice"),
            ("length = decimal", "the type comes first"),
            ("length = float colour=red", "not key=value"),
            ("flag = bool min=0", "min and max are for numbers"),
            ("length = float min=5 max=1", "min is greater than max"),
            ("length = float min=0 max=10 default=20", "outside min and max"),
            ("count = int default=2.5", "whole number"),
            ("turns = uint default=-1", "must not be negative"),
            ("flag = bool default=maybe", "yes or no"),
        ):
            with self.subTest(line=line), self.assertRaises(VariableError) as caught:
                declared(*line.split("\n"))
            self.assertIn(text, caught.exception.message)

    def test_values_are_checked_against_the_declaration(self):
        variables = declared("length = float min=0 max=500 default=10", "air = bool", "text = string")
        self.assertEqual(check_values(variables, {}), {"length": 10.0, "air": False, "text": ""})
        self.assertEqual(check_values(variables, {"length": "25", "air": 1, "text": 5}), {"length": 25.0, "air": True, "text": "5"})
        with self.assertRaises(VariableError):
            check_values(variables, {"length": 900})
        with self.assertRaises(VariableError):
            check_values(variables, {"nothing": 1})

    def test_the_sample_values(self):
        variables = declared("length = float default=10", "air = bool", "text = string")
        self.assertEqual(sample_values(variables, True), {"length": 10.0, "air": True, "text": "Text"})
        self.assertEqual(sample_values(variables, False), {"length": 10.0, "air": False, "text": ""})

    def test_function_names(self):
        taken = frozenset({"rapid", "codes"})
        self.assertEqual(list(read_functions([(1, "bar_feed", "d"), (2, "bar2", "")], taken)), ["bar_feed", "bar2"])
        for entry, text in (((1, "rapid", ""), "name of a section or concept"), ((1, "Bar", ""), "not a function name"), ((1, "x_variables", ""), "may not end")):
            with self.assertRaises(VariableError) as caught:
                read_functions([entry], taken)
            self.assertIn(text, caught.exception.message)


class PostFileTests(unittest.TestCase):
    TEMPLATE = (
        "[functions]\nbar_feed = Open, push, close\n[bar_feed_variables]\nlength = float min=0 max=500 default=30 unit=mm\nair = bool\nremark = string\n"
        "[bar_feed]\n<code open>\n<code move> D<length decimals=1 zeros>[ <air yes=\"A1\">][ <remark upper>]\n<code close>\n"
    ).replace("\\n", "\n")

    def test_a_function_is_written_with_its_variables(self):
        definition = post(self.TEMPLATE)
        self.assertEqual(list(definition.functions), ["bar_feed"])
        engine = TemplatePost(definition)
        self.assertEqual(engine.function("bar_feed"), ["M100", "M101 D30.0", "M102"])
        self.assertEqual(engine.function("bar_feed", {"length": 12.5, "air": True, "remark": "hi"}), ["M100", "M101 D12.5 A1 HI", "M102"])

    def test_a_value_outside_the_limits_or_an_unknown_function_is_an_error_when_written(self):
        from wop.post.base import PostError

        engine = TemplatePost(post(self.TEMPLATE))
        with self.assertRaises(PostError):
            engine.function("bar_feed", {"length": 600})
        with self.assertRaises(PostError):
            engine.function("nothing")

    def test_a_variable_can_only_be_used_in_its_own_concept(self):
        extra = self.TEMPLATE + "[feed]\nG1 X<X> D<length>\n"
        with self.assertRaises(PostFileError) as caught:
            post(extra)
        self.assertIn("unknown token <length>", str(caught.exception))
        self.assertIn("[feed]", str(caught.exception))

    def test_two_concepts_can_have_a_variable_of_the_same_name(self):
        second = "[functions]\na = A\nb = B\n[a_variables]\nlength = float default=1\n[b_variables]\nlength = int default=2\n[a]\nA<length>\n[b]\nB<length>\n"
        engine = TemplatePost(post(second))
        self.assertEqual((engine.function("a"), engine.function("b")), (["A1"], ["B2"]))

    def test_the_problems_name_the_place(self):
        for extra, text in (
            ("[functions]\nrapid = x\n", "[functions] line"),
            ("[functions]\nbar = x\n[bar_variables]\ntool = float\n", "[bar_variables] line"),
            ("[functions]\nbar = x\n[bar]\n<length>\n", "unknown token <length>"),
            ("[functions]\nbar = x\n[bar_variables]\nlength = float\n[bar]\n<length colour>\n", "unknown option"),
            ("[nothing]\nx\n", "unknown section [nothing]"),
            ("[bar_variables]\nlength = float\n", "unknown section [bar_variables]"),
        ):
            with self.subTest(extra=extra), self.assertRaises(PostFileError) as caught:
                post(extra)
            self.assertIn(text, str(caught.exception))

    def test_a_function_without_a_section_writes_nothing_and_its_digits_are_allowed_in_the_name(self):
        engine = TemplatePost(post("[functions]\nbar2 = x\n"))
        self.assertEqual(engine.function("bar2"), [])

    def test_the_sample_output_uses_the_defaults_and_fills_or_empties_the_optional_parts(self):
        definition = post(self.TEMPLATE)
        self.assertEqual(render_sample(definition, "bar_feed", True), ["M100", "M101 D30.0 A1 REMARK", "M102"])
        self.assertEqual(render_sample(definition, "bar_feed", False), ["M100", "M101 D30.0", "M102"])


class SamplePostTests(unittest.TestCase):
    def test_the_example_post_reads_has_no_problem_and_writes_the_bar_feed(self):
        definition = parse_post(SAMPLE.read_text(encoding="utf-8"), "linuxcnc_custom_function")
        engine = TemplatePost(definition)
        self.assertEqual(engine.function("bar_feed"), ["(bar feed 30.0 mm)", "M100", "M101 D30.0", "M102"])
        self.assertEqual(engine.function("bar_feed", {"distance": 25, "pull_back": True}), ["(bar feed 25.0 mm)", "M100", "M101 D25.0 R1", "M102"])
        self.assertEqual(definition.codes["barfeeder_move"].group, "barfeeder")  # a group of the user holds the three codes
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        model = AppModel(settings_path=Path(folder.name) / "settings.json")
        post_id = model.import_post(SAMPLE)
        editor = model.post_editor(post_id)
        self.assertEqual(editor.page_problems(), {})
        self.assertEqual(editor.function_names(), ["bar_feed"])
        self.assertEqual([variable.name for variable in editor.variables("bar_feed")], ["distance", "pull_back"])


class EditorModelTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")
        self.editor = self.model.post_editor("linuxcnc")
        self.editor.shipped = False

    def test_add_a_function_give_it_variables_and_a_template_then_remove_it(self):
        editor = self.editor
        editor.add_function("air_blast", "Blow the chuck clean")
        self.assertEqual(editor.functions(), [("air_blast", "Blow the chuck clean")])
        self.assertEqual(editor.concept_keys()[-1], "air_blast")
        self.assertTrue(editor.is_function("air_blast") and editor.has_section("air_blast"))
        editor.set_codes([*[(n, c, g) for n, c, g in editor.codes()], ("air", "M110", "")])
        editor.set_variables_text("air_blast", "seconds = float min=0 max=10 default=2 unit=s")
        editor.set_section("air_blast", "<code air>\n<code dwell> P<seconds>")
        self.assertEqual(editor.page_problems(), {})
        self.assertEqual(render_sample(parse_post(editor.text, "x"), "air_blast", True), ["M110", "G4 P2"])
        self.assertEqual(editor.token_buttons("air_blast")[0].text, "<seconds>")  # the variables come first
        self.assertEqual(editor.token_buttons("air_blast")[0].group, "Variables")
        editor.remove_function("air_blast")
        self.assertEqual((editor.functions(), editor.has_section("air_blast")), ([], False))
        self.assertNotIn("air_blast", editor.text)

    def test_a_bad_name_is_refused_with_the_reason(self):
        for name, text in (("rapid", "name of a section or concept"), ("My Thing", "not a function name"), ("x_variables", "may not end")):
            with self.assertRaises(ValueError) as caught:
                self.editor.add_function(name, "")
            self.assertIn(text, str(caught.exception))
        self.editor.add_function("fine", "")
        with self.assertRaises(ValueError):
            self.editor.add_function("fine", "")

    def test_a_problem_in_the_variables_marks_the_concept_page(self):
        editor = self.editor
        editor.add_function("fn", "")
        editor.set_variables_text("fn", "tool = float")
        problems = editor.page_problems()
        self.assertIn("fn", problems)
        self.assertIn("[fn_variables] line 1", problems["fn"])
        self.assertIn("start of the token", editor.preview("fn").error)

    def test_the_description_can_be_changed(self):
        self.editor.add_function("fn", "old")
        self.editor.set_function_description("fn", "new")
        self.assertEqual(self.editor.function_description("fn"), "new")


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class WindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")
        self.post_id = self.model.import_post(SAMPLE)
        self.dialog = PostEditorDialog(None, self.model, self.post_id)
        self.addCleanup(self.dialog.deleteLater)

    def row_of(self, text):
        return next(row for row in range(self.dialog._pages.count()) if self.dialog._pages.item(row).text() == text)

    def test_the_list_has_a_custom_concepts_line_and_the_function_below_it(self):
        texts = [self.dialog._pages.item(row).text() for row in range(self.dialog._pages.count())]
        self.assertEqual(texts[-2:], ["Custom concepts", "bar_feed"])
        self.assertEqual(texts[-2:], texts[self.row_of("Custom concepts"):])

    def test_the_page_of_a_function_has_its_description_variables_and_template(self):
        self.dialog._pages.setCurrentRow(self.row_of("bar_feed"))
        self.assertTrue(self.dialog._function_description.text().startswith("Open the bar feeder"))
        self.assertIn("distance = float", self.dialog._variables.toPlainText())
        self.assertIn("<code barfeeder_open>", self.dialog._template.toPlainText())
        self.assertFalse(self.dialog._own.isHidden() is False)  # the "own section" tick is not shown for a custom concept
        self.assertEqual(self.dialog._present.toPlainText().splitlines()[0], "(bar feed 30.0 mm)")
        grid_buttons = [self.dialog._tokens.tabText(i) for i in range(self.dialog._tokens.count())]
        self.assertEqual(grid_buttons[0], "Variables")  # the variables stand first in the token grid

    def test_typing_in_the_variables_box_changes_the_post_and_the_token_grid(self):
        self.dialog._pages.setCurrentRow(self.row_of("bar_feed"))
        self.dialog._variables.setPlainText(self.dialog._variables.toPlainText() + "\nspeed = float default=2")
        self.assertIn("speed = float", self.dialog.editor.text)
        self.assertEqual([v.name for v in self.dialog.editor.variables("bar_feed")], ["distance", "pull_back", "speed"])

    def test_a_mistake_in_the_variables_shows_in_red_and_on_the_list(self):
        self.dialog._pages.setCurrentRow(self.row_of("bar_feed"))
        self.dialog._variables.setPlainText("tool = float")
        self.assertIn("start of the token", self.dialog._problem.text())
        row = self.row_of("bar_feed")
        self.assertEqual(self.dialog._pages.item(row).foreground().color().name(), POST_ERROR_COLOR)

    def test_add_and_remove_a_concept(self):
        answers = iter(["air_blast", "Blow the chuck clean"])
        QInputDialog.getText = staticmethod(lambda *a, **k: (next(answers), True))
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        self.dialog._add_function()
        self.assertEqual(self.dialog._page, "air_blast")
        self.assertEqual(self.dialog.editor.function_names(), ["bar_feed", "air_blast"])
        self.assertTrue(self.dialog._remove_function_button.isEnabled())
        self.dialog._remove_function()
        self.assertEqual(self.dialog.editor.function_names(), ["bar_feed"])
        self.assertEqual(self.dialog._page, "post")

    def test_a_post_that_comes_with_wop_cannot_get_a_concept(self):
        shipped = PostEditorDialog(None, self.model, "linuxcnc")
        self.addCleanup(shipped.deleteLater)
        self.assertFalse(shipped._add_function_button.isEnabled())
        self.assertFalse(shipped._remove_function_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
