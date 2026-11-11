"""Styles of the turning contour block (part of the program): the pocket order, the contract of a roughing style, the pictures and the check."""

import re
import unittest

from tests.test_rough_follow import generate
from tests.test_roughing_rules import DEPTH_OF_CUT, RAW, SHAPES, TOOLS, simulate
from wop.adapters.style_check import check_style
from wop.adapters.style_samples import samples_for
from wop.core.blocks.base import BlockError
from wop.core.blocks.rough_style import Cut, RoughLine, RoughStyleError, checked_cut
from wop.core.blocks.styles import DEFAULT_STYLE_KEY, STYLES, StyleInfo
from wop.core.blocks.turning_common import PassDirection
from wop.core.program_model.operations import Rapid
from wop.ui.style_picture import style_pictures
from wop.ui.theme import LIGHT_COLORS

STYLE = "pockets_last"
DEPTH_TOLERANCE_MM = 0.15  # the depth of the deepest feed move may differ by this much between the styles (the order of the cuts moves a pass)


def masked(messages):
    """The notes without their numbers (the area and the Z of a note differ by a few hundredths when the cuts come in another order)."""
    return tuple(re.sub(r"-?\d+(\.\d+)?", "#", message) for message in messages)


def rapid_length(operations):
    position, total = None, 0.0
    for operation in operations:
        end = getattr(operation, "end", None)
        if end is None:
            continue
        if isinstance(operation, Rapid) and position is not None:
            total += position.distance_to(end)
        position = end
    return total


def line(**overrides):
    values = dict(level=0, radius=10, z_high=0, z_low=-10, kind="open", pocket=-1, layer=-1)
    values.update(overrides)
    return RoughLine(**values)


class ContractTests(unittest.TestCase):
    def test_only_a_pocket_line_can_be_cut_later(self):
        with self.assertRaises(RoughStyleError) as caught:
            checked_cut(line(), Cut(later=True), "mine")
        self.assertIn("'mine'", str(caught.exception))
        self.assertIn("only a pocket line can be cut later", str(caught.exception))
        checked_cut(line(kind="pocket", pocket=0, layer=0), Cut(later=True), "mine")

    def test_the_answer_must_be_a_cut_with_an_order_of_numbers(self):
        for answer, text in ((None, "must return a Cut"), ("later", "must return a Cut"), (Cut(order=("a",)), "tuple of numbers")):
            with self.subTest(answer=answer), self.assertRaises(RoughStyleError) as caught:
                checked_cut(line(), answer, "mine")
            self.assertIn(text, str(caught.exception))

    def test_the_standard_style_says_nothing_special(self):
        self.assertEqual(STYLES.get("turning_contour", DEFAULT_STYLE_KEY).function(line()), Cut())
        self.assertTrue(STYLES.supports("turning_contour"))


class PocketsLastTests(unittest.TestCase):
    def run_shape(self, shape, tool, style, direction=PassDirection.ALONG_Z):
        result, _contour = generate(SHAPES[shape], TOOLS[tool](), RAW, pass_direction=direction, depth_of_cut_mm=DEPTH_OF_CUT, finish_pass=False, style=style)
        return result

    def test_the_style_is_offered(self):
        self.assertEqual([s.key for s in STYLES.styles_for("turning_contour")][:2], [DEFAULT_STYLE_KEY, STYLE])

    def test_every_shape_with_every_tool_removes_what_the_standard_style_removes_and_stays_as_safe(self):
        for shape in SHAPES:
            for tool in TOOLS:
                with self.subTest(shape=shape, tool=tool):
                    standard = self.run_shape(shape, tool, DEFAULT_STYLE_KEY)
                    late = self.run_shape(shape, tool, STYLE)
                    self.assertAlmostEqual(standard.removed.area, late.removed.area, delta=0.05)
                    self.assertEqual(masked(standard.messages), masked(late.messages))  # the same notes; the order of the cuts may move a sliver of a few hundredths
                    standard_deepest, standard_hits = simulate(standard, TOOLS[tool](), RAW, True)
                    deepest, hits = simulate(late, TOOLS[tool](), RAW, True)
                    self.assertEqual(hits, standard_hits)  # no rapid goes through stock that the standard style did not go through
                    self.assertLessEqual(deepest, standard_deepest + DEPTH_TOLERANCE_MM)  # no feed move ends deeper in uncut stock (a pass that is cut after the layer above is not, the same pass is 0.1 mm deeper on the low bump: it touches neither the part nor its allowance)

    def test_across_x_the_style_changes_nothing(self):
        for shape in ("pocket with a ramp behind it", "low bump"):
            standard = self.run_shape(shape, "VNMG 50 degrees", DEFAULT_STYLE_KEY, PassDirection.ALONG_X)
            late = self.run_shape(shape, "VNMG 50 degrees", STYLE, PassDirection.ALONG_X)
            self.assertEqual(standard.operations, late.operations)

    def test_a_style_that_cuts_the_layers_of_a_pocket_in_the_wrong_order_is_refused(self):
        def backwards(rough_line):
            return Cut(later=True, order=(rough_line.pocket, -rough_line.layer)) if rough_line.kind == "pocket" else Cut()

        STYLES.register("turning_contour", StyleInfo("backwards", "Backwards", "", backwards))
        self.addCleanup(STYLES.unregister, "turning_contour", "backwards")
        with self.assertRaises(BlockError) as caught:
            self.run_shape("pocket with a ramp behind it", "VNMG 50 degrees", "backwards")
        self.assertIn("must be cut in their order", str(caught.exception))

    def test_a_style_that_stops_or_answers_wrongly_is_a_reason_not_a_crash(self):
        def crash(_line):
            return 1 / 0

        def wrong(_line):
            return "now"

        for name, function, text in (("crash", crash, "ZeroDivisionError"), ("wrong", wrong, "must return a Cut")):
            STYLES.register("turning_contour", StyleInfo(name, name, "", function))
            self.addCleanup(STYLES.unregister, "turning_contour", name)
            with self.subTest(name=name), self.assertRaises(BlockError) as caught:
                self.run_shape("stepped shaft", "VNMG 50 degrees", name)
            self.assertIn(text, str(caught.exception))

    def test_a_block_whose_style_is_gone_is_refused_with_a_reason_and_still_shows_it(self):
        block, context = samples_for("turning_contour")[0].build("gone")
        with self.assertRaises(BlockError) as caught:
            block.generate(context)
        self.assertIn("'gone' is not available", str(caught.exception))
        self.assertEqual([key for key, _label in block.field_choices()["style"]][-1], "gone")
        self.assertIn("not available in this program", block.form_notes()["style"])


class AnalyticPlannerTests(unittest.TestCase):
    """The styles on the analytic planner (step 3 of the branch, the user's decision 2026-10-25): the style decides the order of the lines;
    the routes are always over the material at one clearance (X12)."""

    TWO_POCKETS = "two pockets behind crests"

    def cuts(self, style, sample=TWO_POCKETS):
        from wop.core.analytic.wanted_lines import LineKind

        block, context = next(s for s in samples_for("turning_contour") if s.name == sample).build(style)
        first = block.roughing_cuts(context)
        return [(c.source.kind is LineKind.POCKET, c.source.pocket, c.source.layer) for c in first.cuts if c.kind.name == "LINE"]

    def test_pockets_last_cuts_every_open_line_before_the_first_pocket_line(self):
        pockets = [pocket for pocket, _number, _layer in self.cuts(STYLE)]
        self.assertEqual(pockets, sorted(pockets))
        self.assertNotEqual(self.cuts(DEFAULT_STYLE_KEY), self.cuts(STYLE))  # the standard style cuts them level by level

    def test_the_front_pocket_comes_first_and_the_layers_of_a_pocket_in_their_order(self):
        late = [(number, layer) for pocket, number, layer in self.cuts(STYLE) if pocket]
        self.assertEqual(late, sorted(late))

    def test_both_styles_remove_the_same_material_with_no_note(self):
        for sample in samples_for("turning_contour"):
            with self.subTest(sample=sample.name):
                results = [sample.build(style)[0].generate(sample.build(style)[1]) for style in (DEFAULT_STYLE_KEY, STYLE)]
                self.assertAlmostEqual(results[0].removed.area, results[1].removed.area, delta=0.05)
                self.assertEqual(results[0].messages, results[1].messages)

    def test_a_style_that_stops_or_answers_wrongly_is_a_reason_not_a_crash(self):
        for name, function, text in (("crash", lambda _line: 1 / 0, "ZeroDivisionError"), ("wrong", lambda _line: "now", "must return a Cut")):
            STYLES.register("turning_contour", StyleInfo(name, name, "", function))
            self.addCleanup(STYLES.unregister, "turning_contour", name)
            block, context = samples_for("turning_contour")[0].build(name)
            with self.subTest(name=name), self.assertRaises(BlockError) as caught:
                block.generate(context)
            self.assertIn(text, str(caught.exception))

    def test_a_style_that_cuts_the_layers_of_a_pocket_in_the_wrong_order_is_refused(self):
        def backwards(rough_line):
            return Cut(later=True, order=(rough_line.pocket, -rough_line.layer)) if rough_line.kind == "pocket" else Cut()

        STYLES.register("turning_contour", StyleInfo("backwards", "Backwards", "", backwards))
        self.addCleanup(STYLES.unregister, "turning_contour", "backwards")
        block, context = next(s for s in samples_for("turning_contour") if s.name == self.TWO_POCKETS).build("backwards")
        with self.assertRaises(BlockError) as caught:
            block.generate(context)
        self.assertIn("must be cut in their order", str(caught.exception))


class CheckAndPicturesTests(unittest.TestCase):
    def test_every_style_that_comes_with_the_program_passes_the_check_on_the_samples(self):
        for block_type in ("grooving", "turning_contour"):
            for info in STYLES.styles_for(block_type):
                if info.key != DEFAULT_STYLE_KEY:
                    with self.subTest(block_type=block_type, style=info.key):
                        self.assertEqual(check_style(block_type, info.key), [])

    def test_the_samples_are_clean_parts_that_the_standard_style_cuts_without_notes(self):
        for sample in samples_for("turning_contour"):
            with self.subTest(sample=sample.name):
                block, context = sample.build(DEFAULT_STYLE_KEY)
                self.assertEqual(block.generate(context).messages, ())

    def test_the_pictures_show_the_rapids_and_the_two_styles_look_different(self):
        standard = style_pictures("turning_contour", DEFAULT_STYLE_KEY, LIGHT_COLORS)
        late = style_pictures("turning_contour", STYLE, LIGHT_COLORS)
        self.assertEqual([p.caption for p in standard], [s.name for s in samples_for("turning_contour")])
        pocket = lambda pictures: next(p for p in pictures if "two pockets" in p.caption).svg  # with one pocket both styles cut alike
        self.assertIn("stroke-dasharray", pocket(standard))  # the rapids are drawn for this block type
        self.assertNotEqual(pocket(standard), pocket(late))

    def test_the_form_has_the_picture_dropdown_and_the_hint_as_a_note(self):
        from wop.ui.block_forms import form_for

        block, _context = samples_for("turning_contour")[0].build(STYLE)
        specs = {s.path[0]: s for s in form_for(block)}
        self.assertEqual(specs["style"].preview, "turning_contour")
        self.assertIn("pocket", specs["style"].note)
        self.assertEqual([c.value for c in specs["style"].choices][:2], [DEFAULT_STYLE_KEY, STYLE])


if __name__ == "__main__":
    unittest.main()
