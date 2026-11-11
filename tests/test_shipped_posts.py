"""The posts that come with WOP (LinuxCNC, and the default post inside the program) and the reference posts of `examples/posts`: they load, they check,
and they write every example project without an error.

This says nothing about what the G-code means for a machine: the user checks that (see the disclaimer in the post files).
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tests.helpers import planned
from tests.post_helpers import REFERENCE_FOLDER, REFERENCE_POSTS, reference_definition, reference_post, reference_text
from wop.adapters.post_library import FALLBACK_POST_ID, SHIPPED_FOLDER, load_post_library
from wop.core.program_model.operations import ArcMove
from wop.core.program_model.units import XInputMode
from wop.post.base import Feature, PostSettings
from wop.post.concepts import CONCEPTS
from wop.post.engine import TemplatePost
from wop.post.post_definition import parse_post

from wop.core.blocks import BLOCK_TYPES  # noqa: F401  (registers the block types)
from wop.core.files.project_io import project_from_json
from wop.post.context import make_context
from wop.post.generate import RemedyKind, find_issues, generate_gcode

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SHIPPED = ("generic", "linuxcnc")  # the default post is part of the program but not in the list of posts
POSTS_TO_TRY = ("linuxcnc", *REFERENCE_POSTS)


class LibraryTests(unittest.TestCase):
    def test_the_shipped_posts_load_without_problems(self):
        library = load_post_library()
        self.assertEqual(library.problems, ())
        self.assertEqual(sorted(library.shipped), sorted(SHIPPED))
        self.assertEqual(library.ids(), ["linuxcnc"])  # the default post is not offered
        for post_id in REFERENCE_POSTS:
            self.assertEqual(reference_definition(post_id).post_id, post_id)

    def test_the_default_post_has_every_section_the_others_may_leave_out(self):
        generic = load_post_library().posts[FALLBACK_POST_ID]
        for name, concept in CONCEPTS.items():
            if concept.needed and name not in ("arc_cw", "arc_ccw", "spindle_css", "thread_cycle", "thread_two_block", "drill_cycle"):
                self.assertIn(name, generic.templates, name)

    def test_capabilities_are_as_before(self):
        posts = load_post_library().posts
        self.assertEqual(posts["linuxcnc"].features, frozenset(Feature))
        self.assertEqual(reference_definition("fanuc").features, frozenset(Feature))
        self.assertNotIn(Feature.CONSTANT_SURFACE_SPEED, posts["generic"].features)
        self.assertNotIn(Feature.DIAMETER_MODE, posts["generic"].features)
        self.assertNotIn(Feature.ARCS_IN_DIAMETER_MODE, posts["generic"].features)
        self.assertEqual(posts["generic"].features, frozenset(Feature) - {Feature.CONSTANT_SURFACE_SPEED, Feature.DIAMETER_MODE, Feature.ARCS_IN_DIAMETER_MODE})

    def test_a_post_that_is_not_found_gives_the_default_and_a_message(self):
        library = load_post_library()
        definition, note = library.choose("linuxcnc")
        self.assertEqual((definition.post_id, note), ("linuxcnc", ""))
        definition, note = library.choose("renamed")
        self.assertEqual(definition.post_id, "linuxcnc")
        self.assertIn("'renamed' was not found", note)

    def test_the_posts_of_the_user_come_from_the_posts_folder_and_the_shipped_ones_win(self):
        with tempfile.TemporaryDirectory() as folder:
            posts = Path(folder) / "posts"
            posts.mkdir()
            (posts / "mine.post.ini").write_text("[post]\nname = Mine\nformat_version = 1\n[rapid]\nG0 X<X>\n", encoding="utf-8")
            (posts / "linuxcnc.post.ini").write_text("[post]\nname = Not LinuxCNC\nformat_version = 1\n", encoding="utf-8")
            (posts / "broken.post.ini").write_text("[post]\nname = x\n", encoding="utf-8")
            library = load_post_library(Path(folder))
        self.assertEqual(library.ids(), ["linuxcnc", "mine"])
        self.assertEqual(library.posts["linuxcnc"].name, "LinuxCNC")
        self.assertEqual(len(library.problems), 2)
        self.assertTrue(any("shipped post" in problem for problem in library.problems))
        self.assertTrue(any("broken.post.ini" in problem for problem in library.problems))
        # a section the user's post lacks comes from the default post
        self.assertIn("M30", TemplatePost(library.posts["mine"]).footer())

    def test_every_shipped_file_says_that_the_user_checks_the_output(self):
        for path in [*SHIPPED_FOLDER.glob("*.post.ini"), *(REFERENCE_FOLDER / f"{post_id}.post.ini" for post_id in REFERENCE_POSTS)]:
            text = path.read_text(encoding="utf-8")
            self.assertTrue("NOTHING" in text or "The user checks what a post writes" in text, path.name)  # the LinuxCNC post was tried on a machine
            self.assertIn("can crash a machine", text, path.name)


def example_plans():
    for path in sorted(EXAMPLES.glob("*/*.wop.json")) + sorted(EXAMPLES.glob("*.wop.json")):
        project = project_from_json(path.read_text(encoding="utf-8"))
        yield path.name, project, planned(project.program)


class EveryExampleTests(unittest.TestCase):
    def test_each_shipped_post_writes_each_example(self):
        library = load_post_library()
        for name, project, plan in example_plans():
            context = make_context(project.program, plan, project.settings.title, "Lathe", datetime(2026, 10, 17))
            for post_id in POSTS_TO_TRY:
                with self.subTest(example=name, post=post_id):
                    post = TemplatePost(library.posts[post_id]) if post_id in library.posts else reference_post(post_id)
                    settings = PostSettings(XInputMode.DIAMETER)
                    accepted = {issue.key for issue in find_issues(plan, post.info, settings) if issue.key is not None}
                    result = generate_gcode(plan, post, settings, accepted, context=context)
                    self.assertTrue(result.text.strip())
                    self.assertEqual(result.complete, not result.skipped_blocks)
                    for index in result.skipped_blocks:  # a block is only left out for a problem without a remedy
                        self.assertTrue(any(i.block_index == index and i.remedy is None for i in result.issues), (post_id, name, index))
                    self.assertNotIn("<", result.text.replace("<=", ""), "an unresolved token?")

    def test_linuxcnc_and_fanuc_write_cutter_compensation_when_it_is_switched_on(self):
        library = load_post_library()
        project = project_from_json((EXAMPLES.parent / "tests" / "data" / "projects" / "compensation_test.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        for post_id in ("linuxcnc", "fanuc"):
            text = reference_text(post_id) if post_id == "fanuc" else library.path_of(post_id).read_text(encoding="utf-8")
            as_shipped = "yes" if post_id == "linuxcnc" else "no"  # the LinuxCNC post was tried on the machine (2026-10-26)
            self.assertIn(f"cutter_compensation = {as_shipped}", text)
            for setting in ("no", "yes"):
                with self.subTest(post=post_id, compensation=setting):
                    definition = parse_post(text.replace(f"cutter_compensation = {as_shipped}", f"cutter_compensation = {setting}").replace("line_numbers = yes", "line_numbers = no"), post_id, library.posts["generic"])
                    post = TemplatePost(definition)
                    settings = PostSettings(XInputMode.DIAMETER)
                    accepted = {issue.key for issue in find_issues(plan, post.info, settings) if issue.key is not None}
                    lines = generate_gcode(plan, post, settings, accepted).text.splitlines()
                    starts = [line for line in lines if line.startswith(("G41", "G42"))]
                    ends = [line for line in lines if line.startswith("G40")]  # the header line starts with G18
                    self.assertEqual((len(starts), len(ends)), (1, 1) if setting == "yes" else (0, 0))

    def test_a_post_without_diameter_mode_needs_one_remedy_and_keeps_its_arcs(self):
        # Regression: the generic post asked for the radius values and also for the arcs to become short lines.
        library = load_post_library()
        for name, _project, plan in example_plans():
            if not any(isinstance(op, ArcMove) for op in plan.operations):
                continue
            with self.subTest(example=name):
                post = TemplatePost(library.posts["generic"])
                settings = PostSettings(XInputMode.DIAMETER)
                issues = find_issues(plan, post.info, settings)
                self.assertFalse([i for i in issues if i.remedy is RemedyKind.ARCS_AS_LINES], issues)
                accepted = {i.key for i in issues if i.key is not None}
                self.assertRegex(generate_gcode(plan, post, settings, accepted).text, r"G[23] X")

    def test_the_arcs_of_the_examples_are_written_as_arcs_where_the_post_has_them(self):
        library = load_post_library()
        for name, project, plan in example_plans():
            if not any(isinstance(op, ArcMove) for op in plan.operations):
                continue
            with self.subTest(example=name):
                post = TemplatePost(library.posts["linuxcnc"])
                settings = PostSettings(XInputMode.RADIUS)
                text = generate_gcode(plan, post, settings, set()).text
                self.assertRegex(text, r"G[23] X")


if __name__ == "__main__":
    unittest.main()
