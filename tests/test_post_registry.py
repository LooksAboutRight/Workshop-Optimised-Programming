"""The token registry, the concept list, and the engine inside the generator (with the example projects)."""

import unittest
from datetime import datetime
from pathlib import Path

from tests.helpers import planned
from wop.core.program_model.operations import ArcMove, LinearMove, ToolChange
from wop.core.program_model.units import XInputMode
from wop.post.base import PostSettings
from wop.post.concepts import CONCEPTS
from tests.post_helpers import ALL_FEATURES
from wop.post.engine import TemplatePost
from wop.post.post_definition import parse_post
from wop.post.tokens import TOKENS, find_token

from wop.core.blocks import BLOCK_TYPES  # noqa: F401  (registers the block types)
from wop.core.files.project_io import project_from_json
from wop.post.context import make_context
from wop.post.generate import find_issues, generate_gcode

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
KINDS = ("number", "text", "lines")
FORMATS = ("coordinate", "feed", "speed", "one", "count")


class RegistryTests(unittest.TestCase):
    def test_every_token_is_described_and_has_an_example(self):
        for token in TOKENS.values():
            with self.subTest(token=token.name):
                self.assertTrue(token.description.strip())
                self.assertIn(token.kind, KINDS)
                if token.kind != "lines":
                    self.assertTrue(token.example.strip() or token.kind == "text", token.name)
                self.assertIn(token.number_format, FORMATS)

    def test_every_token_works_in_concepts_that_exist(self):
        for token in TOKENS.values():
            with self.subTest(token=token.name):
                self.assertTrue(token.concepts is None or token.concepts <= set(CONCEPTS), token.concepts)

    def test_number_tokens_accept_the_number_options(self):
        for token in TOKENS.values():
            if token.kind == "number":
                with self.subTest(token=token.name):
                    self.assertTrue({"decimals", "zeros", "prefix"} <= token.options)

    def test_the_longest_name_wins(self):
        self.assertEqual(find_token(("tool", "number", "prefix=T"))[0].name, "tool number")
        self.assertEqual(find_token(("previous", "tool", "number"))[0].name, "previous tool number")
        self.assertEqual(find_token(("X", "start", "incremental"))[0].name, "X start")
        self.assertEqual(find_token(("X", "incremental"))[0].name, "X")
        self.assertIsNone(find_token(("nothing",)))

    def test_the_name_lists_are_complete(self):
        names = set(TOKENS)
        for selector in ("tool", "previous tool", "next tool", "first tool", "last tool"):
            for field_name in ("number", "name", "offset", "type", "material", "nose radius", "tip direction"):
                self.assertIn(f"{selector} {field_name}", names)

    def test_every_concept_has_a_description(self):
        self.assertTrue(all(concept.description for concept in CONCEPTS.values()))


def recording_post() -> TemplatePost:
    """A post whose every concept writes its own name: proves the generator reaches each one."""
    sections = "\n".join(f"[{name}]\n{name}" for name in CONCEPTS if name not in ("tool_entry", "note_entry"))
    text = f"[post]\nname = Recording\nformat_version = 1\n{ALL_FEATURES}{sections}\n"
    return TemplatePost(parse_post(text, "recording"))


def example_programs():
    for path in sorted(EXAMPLES.glob("*/*.wop.json")) + sorted(EXAMPLES.glob("*.wop.json")):
        project = project_from_json(path.read_text(encoding="utf-8"))
        yield path.name, project, planned(project.program)


class GeneratorTests(unittest.TestCase):
    def test_the_generator_reaches_every_concept_of_the_examples(self):
        seen = set()
        for name, _project, plan in example_programs():
            with self.subTest(example=name):
                settings = PostSettings(XInputMode.DIAMETER)
                accepted = {issue.key for issue in find_issues(plan, recording_post().info, settings) if issue.key is not None}
                result = generate_gcode(plan, recording_post(), settings, accepted)
                self.assertTrue(result.text.strip())
                seen |= set(result.text.split())
        self.assertTrue({"header", "footer", "block_start", "rapid", "feed", "tool_change", "spindle_css"} <= seen, seen)

    def test_the_line_ending_of_the_post_is_used(self):
        _name, _project, plan = next(example_programs())
        crlf = TemplatePost(parse_post("[post]\nname = x\nformat_version = 1\n[settings]\nline_ending = crlf\n[header]\nH\n", "x"))
        self.assertEqual(crlf.line_ending, "\r\n")

    def test_the_context_knows_tools_blocks_and_the_order_of_the_tool_changes(self):
        for name, project, plan in example_programs():
            with self.subTest(example=name):
                now = datetime(2026, 10, 17, 9, 30)
                context = make_context(project.program, plan, project.settings.title, "Lathe", now)
                changes = [op.tool_number for op in plan.operations if isinstance(op, ToolChange)]
                self.assertEqual(context.tool_sequence, tuple(changes))
                self.assertEqual(len(context.blocks), len(plan.blocks))
                self.assertEqual(set(context.tools), set(changes))
                if any(isinstance(op, (LinearMove, ArcMove)) for op in plan.operations):
                    self.assertGreater(context.path_length_mm, 0)
                    self.assertGreater(context.estimated_time_min, 0)
                else:  # stops only: at most the rapids to the safe point
                    self.assertGreaterEqual(context.path_length_mm, 0)
                self.assertEqual(context.now, now)

    def test_rapids_are_timed_with_the_speeds_of_the_machine(self):
        from wop.core.geometry import Point
        from wop.core.program_model.operations import Rapid
        from wop.post.context import _path_summary

        moves = [Rapid(Point(0, 0)), Rapid(Point(30, 40))]
        self.assertAlmostEqual(_path_summary(moves, (3000, 8000))[1], 0.01)  # X 30 mm at 3000, Z 40 mm at 8000: X is slower
        self.assertAlmostEqual(_path_summary(moves, (None, None))[1], 50 / 5000)  # no speeds: the fixed rate
        self.assertAlmostEqual(_path_summary(moves, (None, None))[0], 50)

    def test_a_post_that_uses_the_context_through_the_generator(self):
        _name, project, plan = next(example_programs())
        text = (
            f"[post]\nname = Ctx\nformat_version = 1\n{ALL_FEATURES}"
            "[header]\nTOOLS <tool count> BLOCKS <block count> FIRST <first tool name>\n"
            "[block_start]\nB<block number> <block type>\n"
            + "".join(f"[{c}]\n{c}\n" for c in CONCEPTS if c not in ("header", "block_start", "tool_entry", "note_entry"))
        )
        context = make_context(project.program, plan, "", "Lathe", datetime(2026, 1, 1))
        post = TemplatePost(parse_post(text, "ctx"))
        settings = PostSettings(XInputMode.RADIUS)
        accepted = {issue.key for issue in find_issues(plan, post.info, settings) if issue.key is not None}
        result = generate_gcode(plan, post, settings, accepted, context=context)
        lines = result.text.splitlines()
        self.assertEqual(lines[0], f"TOOLS {len(context.tools_in_use)} BLOCKS {len(plan.blocks)} FIRST {context.tools_in_use[0].name}")
        self.assertIn(f"B1 {plan.blocks[0].block.type_name}", lines)


if __name__ == "__main__":
    unittest.main()
