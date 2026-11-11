"""The post editor without a window: the sections of a post file, the sample output, the model and the actions of AppModel."""

import tempfile
import unittest
from pathlib import Path

from tests.post_helpers import reference_definition, reference_text
from wop.adapters.post_library import FALLBACK_POST_ID, load_post_library
from wop.core.lathe.machine import MachineDef
from wop.core.program_model.units import XInputMode
from wop.post.base import Feature, PostError
from wop.post.concepts import CONCEPTS
from wop.post.post_definition import parse_post
from wop.post.post_text import PostText, entries, set_key
from wop.post.samples import render_sample
from wop.ui.app_model import AppModel, ModelError
from wop.ui.post_editor_model import PostEditorModel

LIBRARY = load_post_library()
SHIPPED_TEXT = {post_id: LIBRARY.path_of(post_id).read_text(encoding="utf-8") for post_id in ("generic", "linuxcnc")}
SHIPPED_TEXT["fanuc"] = reference_text("fanuc")  # a reference post of examples/posts: not shipped, but it is a good second post for the editor
HEAD = "[post]\nname = Inline\nformat_version = 1\n"


def editor(post_id="linuxcnc", shipped=True):
    fallback = None if post_id == FALLBACK_POST_ID else LIBRARY.posts[FALLBACK_POST_ID]
    return PostEditorModel(post_id, SHIPPED_TEXT[post_id], shipped, fallback)


def sample(text, concept, present):
    return render_sample(parse_post(HEAD + text, "inline"), concept, present)


class PostTextTests(unittest.TestCase):
    def test_a_file_comes_back_as_it_was_with_its_comments(self):
        for post_id, text in SHIPPED_TEXT.items():
            with self.subTest(post=post_id):
                again = PostText.from_text(text).to_text()
                self.assertEqual(parse_post(again, post_id).sources, parse_post(text, post_id).sources)
                self.assertTrue(again.startswith("#"))  # the comment at the top stays

    def test_a_section_is_changed_and_a_new_one_goes_to_its_place(self):
        text = PostText.from_text(HEAD + "\n[feed]\nA\n\n[footer]\nB\n")
        text.set_body("feed", "C\nD")
        text.set_body("rapid", "E")
        text.set_body("settings", "decimals = 2")
        self.assertEqual(list(text.sections), ["post", "settings", "rapid", "feed", "footer"])
        self.assertEqual(text.body("feed"), "C\nD")
        text.remove("feed")
        self.assertFalse(text.has("feed"))

    def test_key_value_lines(self):
        body = "# a comment\ndecimals = 3\nzeros = no\n\n"
        self.assertEqual(entries(body), [(2, "decimals", "3"), (3, "zeros", "no")])
        self.assertEqual(set_key(body, "decimals", "2").split("\n")[1], "decimals = 2")
        self.assertIn("point = yes", set_key(body, "point", "yes"))
        self.assertEqual(set_key("", "a", "1"), "a = 1")


class SampleTests(unittest.TestCase):
    def test_sample_output_of_the_shipped_posts(self):
        linuxcnc, fanuc = LIBRARY.posts["linuxcnc"], reference_definition("fanuc")
        self.assertEqual(render_sample(linuxcnc, "feed", True), ["G1 X25 Z-3 F0.2"])
        self.assertEqual(render_sample(linuxcnc, "feed", False), [])  # nothing changed: no G1, no X, no Z, no F, so no line
        self.assertEqual(render_sample(linuxcnc, "feed", True, XInputMode.RADIUS), ["G1 X12.5 Z-3 F0.2"])
        self.assertEqual(render_sample(linuxcnc, "spindle_css", True), ["G96 D3000 S120 M3"])
        self.assertEqual(render_sample(linuxcnc, "spindle_css", False), ["G96 S120 M3"])  # the spindle codes are written every time, no limit
        self.assertEqual(render_sample(fanuc, "spindle_css", True), ["G50 S3000", "G96 S120 M3"])
        self.assertEqual(render_sample(fanuc, "spindle_css", False), ["G96 S120 M3"])
        self.assertEqual(render_sample(fanuc, "tool_change", True), ["T0101"])
        self.assertTrue(render_sample(linuxcnc, "thread_cycle", True)[0].endswith("E3 L3"))
        self.assertFalse(render_sample(linuxcnc, "thread_cycle", False)[0].endswith("L3"))
        self.assertTrue(render_sample(linuxcnc, "thread_cycle", True)[0].startswith("G76 P1.5 Z-20 I-2 J0.4 K1.84 "))  # I, J, K are diameter values in G7 mode
        self.assertTrue(render_sample(linuxcnc, "thread_cycle", True, XInputMode.RADIUS)[0].startswith("G76 P1.5 Z-20 I-1 J0.2 K0.92 "))

    def test_header_has_the_notes_only_in_the_present_case(self):
        header_present = render_sample(LIBRARY.posts["linuxcnc"], "header", True)
        header_absent = render_sample(LIBRARY.posts["linuxcnc"], "header", False)
        self.assertIn("(a note for the operator)", header_present)
        self.assertNotIn("(a note for the operator)", header_absent)

    def test_neighbours_of_tools_and_blocks_exist_only_in_the_present_case(self):
        text = (
            "[tool_change]\n[next <next tool number>] [prev <previous tool number>]\nT<tool number>\n"
            "[block_start]\n<block number>/<block count>[ next <next block name>][ was <previous block name>]\n"
        )
        self.assertEqual(sample(text, "tool_change", True), ["next 2 prev 3", "T1"])
        self.assertEqual(sample(text, "tool_change", False), ["T1"])  # the first line has only empty tokens: gone
        self.assertEqual(sample(text, "block_start", True), ["2/3 next Finish was Face"])
        self.assertEqual(sample(text, "block_start", False), ["1/1"])

    def test_changed_is_forced_in_both_cases_for_positions_and_codes(self):
        text = "[codes]\nrapid = Q0\n[modal_groups]\nmotion = Q0\n[rapid]\n<code rapid changed> [X<X changed>] [Z<Z changed>] <N next>\n"
        self.assertEqual(sample(text, "rapid", True), ["Q0 X25 Z-3 N10"])
        self.assertEqual(sample(text, "rapid", False), ["N10"])

    def test_the_sample_is_the_same_every_time(self):
        for concept in CONCEPTS:
            try:
                first = render_sample(LIBRARY.posts["linuxcnc"], concept, True)
            except PostError:
                continue
            self.assertEqual(first, render_sample(LIBRARY.posts["linuxcnc"], concept, True), concept)

    def test_every_concept_of_every_shipped_post_has_a_sample_or_says_why_not(self):
        for post_id, definition in LIBRARY.posts.items():
            for concept in CONCEPTS:
                for present in (True, False):
                    with self.subTest(post=post_id, concept=concept, present=present):
                        try:
                            render_sample(definition, concept, present)
                        except PostError as error:
                            self.assertIn("no default post", str(error))  # only a concept nobody has


class EditorModelTests(unittest.TestCase):
    def test_nothing_changed_is_not_dirty_and_a_change_is(self):
        model = editor("linuxcnc", shipped=False)
        self.assertFalse(model.dirty)
        self.assertIsNone(model.problem())
        model.set_section("feed", "G1 X<X>")
        self.assertTrue(model.dirty)

    def test_settings_codes_and_the_derived_features_are_written_into_the_text(self):
        model = editor("linuxcnc", shipped=False)
        model.set_setting("decimals", "2")
        self.assertEqual(model.settings().decimals, 2)
        before = model.codes()
        model.set_codes([*before, ("zz", "Q99", "")])
        self.assertEqual(model.codes(), [*before, ("zz", "Q99", "")])
        self.assertEqual(model.code_table()["zz"].text, "Q99")
        model.set_setting("x_diameters", "no")
        self.assertNotIn(Feature.DIAMETER_MODE, parse_post(model.text, "x").features)  # the features follow the settings and the codes
        self.assertNotIn("[supports]", model.text)
        model.set_meta("name", "Mine")
        self.assertEqual(model.name, "Mine")
        self.assertIsNone(model.problem())

    def test_the_fixed_codes_are_listed_first_and_an_empty_one_is_not_written(self):
        model = editor("generic", shipped=False)
        rows = model.code_rows()
        fixed = [row for row in rows if row[3]]
        self.assertEqual([row[0] for row in fixed][:3], ["rapid", "feed", "arc_ccw"])
        self.assertEqual(dict((row[0], row[1]) for row in fixed)["css"], "")  # generic has no constant surface speed
        self.assertEqual(dict((row[0], row[1]) for row in fixed)["program_end"], "M30")
        model.set_code_rows([(name, "Q1" if name == "css" else code) for name, code, _g, _f, _m in rows if True] + [("my_code", "M55")])
        self.assertIn("css = Q1", model.text)
        self.assertNotIn("cycle_cancel", model.text)  # an empty fixed code stays out of the file
        self.assertIn("my_code = M55", model.text)
        self.assertEqual(model.code_rows()[-1][:2], ("my_code", "M55"))
        self.assertIn(Feature.CONSTANT_SURFACE_SPEED, parse_post(model.text, "x").features)

    def test_the_work_offsets_are_a_numbered_list_in_the_code_table(self):
        self.assertEqual(LIBRARY.posts["linuxcnc"].work_offsets, ("G54", "G55", "G56", "G57", "G58", "G59", "G59.1", "G59.2", "G59.3"))
        self.assertEqual(LIBRARY.posts["generic"].work_offsets, ())  # a post that does not choose a work offset has none
        model = editor("linuxcnc", shipped=False)
        self.assertEqual([row[0] for row in model.work_offset_rows()][:2], ["work_offset_1", "work_offset_2"])
        self.assertEqual(model.ungrouped_codes(), [])  # the offsets are in the modal group coordinate_system
        self.assertNotIn("work_offset_1", [row[0] for row in model.code_rows()])  # they are not "codes of the user"
        rows = [(name, code) for name, code, _group, _fixed, _meaning in model.code_rows() if True]
        offsets = [(model.work_offset_name(number), code) for number, code in enumerate(["G54", "G55", "G54.1 P1", ""], 1)]
        model.set_code_rows([*rows, *offsets])
        self.assertEqual(parse_post(model.text, "x").work_offsets, ("G54", "G55", "G54.1 P1"))  # an empty offset is not written
        self.assertNotIn("work_offset_4", model.text)

    def test_a_code_written_out_in_a_template_gets_a_hint_not_a_problem(self):
        model = editor("linuxcnc", shipped=False)
        model.set_section("footer", "M30\n(M30 in a comment)\n<text>M30</text>")
        self.assertEqual(model.literal_hints("footer"), ["M30 is in the code table as program_end: write <code program_end>"])
        self.assertIsNone(model.problem())
        self.assertEqual(model.literal_hints("setup"), [])

    def test_a_problem_in_a_template_has_line_and_column(self):
        model = editor("linuxcnc", shipped=False)
        model.set_section("feed", "G1 X<X>\nG1 Y<Y>")
        preview = model.preview("feed")
        self.assertIn("unknown token <Y>", preview.error)
        self.assertEqual((preview.line, preview.column), (2, 5))
        self.assertIsNotNone(model.problem())

    def test_a_problem_in_another_concept_does_not_stop_the_sample(self):
        model = editor("linuxcnc", shipped=False)
        model.set_section("rapid", "G0 <Y>")
        self.assertEqual(model.preview("feed").present, ("G1 X25 Z-3 F0.2",))

    def test_a_concept_from_the_default_post(self):
        model = editor("linuxcnc", shipped=False)
        self.assertEqual(model.preview("thread_passes").note, "this post has no section of its own: the default post writes it")
        self.assertTrue(model.preview("thread_passes").present)
        self.assertTrue(model.default_section("thread_passes").startswith("(thread as plain passes"))
        text = model.own_from_default("thread_passes")
        self.assertTrue(model.has_section("thread_passes"))
        self.assertEqual(model.section("thread_passes"), text)
        model.use_default("thread_passes")
        self.assertFalse(model.has_section("thread_passes"))

    def test_a_concept_nobody_has_says_so(self):
        preview = editor("generic", shipped=False).preview("thread_two_block")
        self.assertIn("neither in this post nor in the default post", preview.error)

    def test_the_token_grid_offers_the_tokens_of_the_concept_and_the_codes_of_the_table(self):
        model = editor("linuxcnc")
        texts = [button.text for button in model.token_buttons("rapid")]
        self.assertIn("<X>", texts)
        self.assertIn("<code rapid>", texts)
        self.assertNotIn("<pitch>", texts)
        self.assertIn("<pitch>", [button.text for button in model.token_buttons("thread_cycle")])
        groups = {button.group for button in model.token_buttons("rapid")}
        self.assertIn("Position", groups)

    def test_a_new_post_is_a_copy_of_the_default_post(self):
        with tempfile.TemporaryDirectory() as folder:
            app = AppModel(settings_path=Path(folder) / "settings.json")
            new = app.new_post_editor()
            self.assertEqual((new.post_id, new.name, new.dirty), ("", "New post", False))
            self.assertIsNone(new.problem())
            self.assertTrue(new.text.startswith("# My post."))


class AppModelPostTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = AppModel(settings_path=Path(self.folder.name) / "settings.json")

    def test_a_shipped_post_cannot_be_saved_or_deleted_under_its_own_name(self):
        shipped = self.model.post_editor("linuxcnc")
        self.assertTrue(shipped.shipped)
        with self.assertRaises(ModelError):
            self.model.save_post(shipped, "linuxcnc")
        with self.assertRaises(ModelError):
            self.model.delete_post("linuxcnc")

    def test_save_as_copy_load_change_save_delete(self):
        copy = self.model.post_editor("linuxcnc")
        post_id = self.model.save_post(copy, self.model.unique_post_id("My Lathe"))
        self.assertEqual(post_id, "my_lathe")
        self.assertIn("my_lathe", self.model.post_library.posts)
        self.assertFalse(copy.shipped)
        self.assertEqual(dict(self.model.post_choices())["my_lathe"], "LinuxCNC [my_lathe]")  # the same name twice: the id tells them apart
        again = self.model.post_editor("my_lathe")
        again.set_section("footer", "M2")
        self.assertTrue(again.dirty)
        self.model.save_post(again)
        self.assertEqual(self.model.post_editor("my_lathe").section("footer"), "M2")
        self.model.delete_post("my_lathe")
        self.assertNotIn("my_lathe", self.model.post_library.posts)

    def test_ids_are_unique_and_safe(self):
        self.assertEqual(self.model.unique_post_id("My Lathe!"), "my_lathe")
        self.assertEqual(self.model.unique_post_id("linuxcnc"), "linuxcnc_2")
        self.assertEqual(self.model.unique_post_id("???"), "post")

    def test_a_new_post_is_saved_under_the_name_and_works(self):
        new = self.model.new_post_editor()
        new.set_meta("name", "Brand new")
        post_id = self.model.save_post(new, self.model.unique_post_id("Brand new"))
        self.assertEqual(post_id, "brand_new")
        self.assertEqual(self.model.post_library.posts["brand_new"].name, "Brand new")

    def test_import_gives_the_file_a_free_name_and_takes_a_file_with_problems(self):
        source = Path(self.folder.name) / "elsewhere.post.ini"
        source.write_text(SHIPPED_TEXT["generic"], encoding="utf-8")
        self.assertEqual(self.model.import_post(source), "elsewhere")
        bad = Path(self.folder.name) / "bad.post.ini"
        bad.write_text("[post]\nname = x\n", encoding="utf-8")
        self.assertEqual(self.model.import_post(bad), "bad")  # it has problems: the editor opens it, nothing else uses it
        self.assertIn("bad", self.model.post_library.unfinished)
        binary = Path(self.folder.name) / "binary.post.ini"
        binary.write_bytes(bytes([255, 254, 0, 1]))
        with self.assertRaises(ModelError):  # not text at all: nothing to open in the editor
            self.model.import_post(binary)
        taken = Path(self.folder.name) / "linuxcnc.post.ini"
        taken.write_text(SHIPPED_TEXT["generic"], encoding="utf-8")
        self.assertEqual(self.model.import_post(taken), "linuxcnc_2")

    def test_without_a_settings_folder_there_is_no_place_for_own_posts(self):
        memory = AppModel()
        with self.assertRaises(ModelError):
            memory.save_post(memory.post_editor("linuxcnc"), "mine")
        self.assertIsNone(memory.posts_folder_path())
        self.assertIsNone(memory.user_folder)

    def test_a_missing_post_has_no_editor(self):
        with self.assertRaises(ModelError):
            self.model.post_editor("nothing")

    def test_the_post_of_the_machine_writes_the_program(self):
        editor_model = self.model.post_editor("linuxcnc")
        editor_model.set_section("footer", "(MY END)\nM30")
        self.model.save_post(editor_model, "my_end")
        self.model.set_machine(MachineDef("m", postprocessor="my_end"))
        self.assertIn("(MY END)", self.model.gcode().text)
        self.model.delete_post("my_end")  # the file is gone: the default post and a line in the header
        text = self.model.gcode().text
        self.assertNotIn("(MY END)", text)
        self.assertIn("'my_end' was not found", text)


if __name__ == "__main__":
    unittest.main()
