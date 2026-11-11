import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace

from tests import svg_demo
from wop.core.program_model.program import plan_program
from wop.ui.svg_preview import legend_for, render_svg
from wop.ui.theme import DARK_COLORS, LIGHT_COLORS

SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"


def count(root, tag):
    return len(list(root.iter(SVG_NAMESPACE + tag)))


class SvgPreviewTests(unittest.TestCase):
    def setUp(self):
        self.demo = svg_demo
        self.plan = plan_program(self.demo.outside_program())

    def test_extra_points_keep_the_picture_from_jumping_and_make_it_smaller(self):
        from wop.core.geometry import Point

        plain = ET.fromstring(render_svg(self.plan))
        far = ET.fromstring(render_svg(self.plan, extra_points=(Point(500, 500),)))
        height = lambda root: float(root.get("height"))  # noqa: E731
        self.assertGreater(height(far), height(plain))  # the radius range grew, so the drawing is smaller in it

    def test_the_picture_is_fitted_to_the_part_and_the_cutting_moves_not_to_the_rapids(self):
        from wop.core.geometry import Point
        from wop.core.program_model.operations import Rapid, plain_moves
        from wop.ui.svg_preview import _extent_points

        moves = [m for op in self.plan.operations for m in plain_moves(op)]
        cutting_ends = {m.end for m in moves if not isinstance(m, Rapid) and isinstance(getattr(m, "end", None), Point)}
        rapid_only = {m.end for m in moves if isinstance(m, Rapid)} - cutting_ends
        self.assertTrue(rapid_only)
        self.assertFalse(rapid_only & set(_extent_points(self.plan)))

    def test_line_scale_thins_lines_dashes_and_marks_for_an_enlarged_picture(self):
        def widths(text):
            root = ET.fromstring(text)
            return [float(e.get("stroke-width")) for e in root.iter() if e.get("stroke-width")]

        whole, zoomed = widths(render_svg(self.plan)), widths(render_svg(self.plan, line_scale=0.1))
        self.assertEqual(len(whole), len(zoomed))
        for before, after in zip(whole, zoomed):
            self.assertAlmostEqual(after, before * 0.1, places=3)
        self.assertEqual(render_svg(self.plan, line_scale=1.0), render_svg(self.plan))
        self.assertIn('stroke-dasharray="0.6 0.4"', render_svg(self.plan, line_scale=0.1))  # the rapid moves
        root = ET.fromstring(render_svg(self.plan, line_scale=0.025))
        sizes = [float(e.get("font-size")) for e in root.iter() if e.get("font-size")]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 1)  # Qt warns about a font of less than one pixel; the text is scaled instead

    def test_the_far_side_of_the_part_is_drawn_first_in_its_own_colour(self):
        from wop.ui.theme import LIGHT_COLORS
        root = ET.fromstring(render_svg(self.plan))
        paths = list(root.iter(SVG_NAMESPACE + "path"))
        self.assertEqual(paths[0].get("fill"), LIGHT_COLORS.far_side_fill)  # first = underneath everything

    def test_picture_is_valid_svg_with_the_expected_parts(self):
        root = ET.fromstring(render_svg(self.plan))
        self.assertEqual(root.tag, SVG_NAMESPACE + "svg")
        self.assertEqual(count(root, "path"), 3)  # the far side of the material, raw part and material left
        self.assertGreater(count(root, "polyline"), 0)  # cutting moves
        dashed = [e for e in root.iter(SVG_NAMESPACE + "line") if e.get("stroke-dasharray") == self.demo_rapid_dash()]
        self.assertGreater(len(dashed), 0)  # rapid moves

    def demo_rapid_dash(self):
        from wop.ui import ui_constants

        return ui_constants.RAPID_DASH

    def test_picture_can_be_limited_to_a_block(self):
        whole = ET.fromstring(render_svg(self.plan))
        first = ET.fromstring(render_svg(self.plan, 0))
        self.assertLess(count(first, "polyline"), count(whole, "polyline"))

    def test_block_names_are_in_the_legend(self):
        text = render_svg(self.plan)
        self.assertIn("1: facing face", text)
        self.assertIn("3: turning second step, transverse", text)

    def test_the_picture_without_legend_holds_only_the_drawing(self):
        text = render_svg(self.plan, with_legend=False)
        self.assertNotIn("1: facing", text)
        self.assertNotIn("dashed = rapid moves", text)
        self.assertLess(len(text), len(render_svg(self.plan)))

    def test_the_size_of_the_picture_does_not_depend_on_the_block_shown(self):
        import re

        boxes = {
            re.search(r'viewBox="([^"]+)"', render_svg(self.plan, upto, with_legend=False)).group(1)
            for upto in (None, 0, 1, 2)
        }
        self.assertEqual(len(boxes), 1)
        with_legend = {
            re.search(r'viewBox="([^"]+)"', render_svg(self.plan, upto)).group(1) for upto in (0, 2)
        }
        self.assertEqual(len(with_legend), 2)  # the old picture grew with its legend: that is why the window has none

    def test_a_colour_set_without_background_draws_none_and_a_background_has_the_full_size(self):
        window = replace(LIGHT_COLORS, background=None)
        self.assertNotIn("<rect", render_svg(self.plan, colors=window))
        root = ET.fromstring(render_svg(self.plan))
        rect = next(root.iter(SVG_NAMESPACE + "rect"))
        self.assertEqual(rect.get("width"), root.get("width"))
        self.assertAlmostEqual(float(rect.get("height")), float(root.get("height")), places=1)
        self.assertNotIn("%", rect.get("width") + rect.get("height"))

    def test_the_colours_of_the_set_are_used(self):
        light, dark = render_svg(self.plan), render_svg(self.plan, colors=DARK_COLORS)
        self.assertIn(LIGHT_COLORS.residual_fill, light)
        self.assertNotIn(LIGHT_COLORS.residual_fill, dark)
        self.assertIn(DARK_COLORS.residual_fill, dark)
        self.assertIn(DARK_COLORS.block_colors[0], dark)

    def test_the_legend_data_names_the_blocks_shown(self):
        whole = legend_for(self.plan)
        self.assertEqual(len(whole.blocks), len(self.plan.blocks))
        self.assertTrue(whole.blocks[0][1].startswith("1: facing"))
        self.assertEqual(whole.blocks[0][0], LIGHT_COLORS.block_colors[0])
        self.assertEqual(len(legend_for(self.plan, 0).blocks), 1)
        self.assertEqual(len(whole.key), 3)
        with self.assertRaises(ValueError):
            legend_for(self.plan, 99)

    def test_no_such_block(self):
        with self.assertRaises(ValueError):
            render_svg(self.plan, 7)

    def test_a_program_without_blocks_shows_just_the_raw_part(self):
        from dataclasses import replace

        empty = plan_program(replace(self.demo.outside_program(), blocks=()))
        ET.fromstring(render_svg(empty))
        with self.assertRaises(ValueError):
            render_svg(empty, 0)

    def test_demo_programs_make_a_picture_of_the_whole_program_and_of_every_block(self):
        for program, blocks in ((self.demo.outside_program(), 3), (self.demo.tube_program(), 2)):
            plan = plan_program(program)
            self.assertEqual(len(plan.blocks), blocks)
            ET.fromstring(render_svg(plan))
            for index in range(blocks):
                ET.fromstring(render_svg(plan, index))


if __name__ == "__main__":
    unittest.main()
