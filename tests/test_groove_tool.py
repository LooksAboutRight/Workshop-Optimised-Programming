import unittest
from dataclasses import replace

from tests.helpers import is_valid_outline
from wop.core.geometry import ArcSegment
from wop.core.tooling.tool import ToolError, ToolSegmentRole
from wop.core.tooling.tool_reference import tip_of, with_tip_at_origin
from wop.core.tool_types import TOOL_TYPES, make_tool
from wop.core.tool_types.groove import TouchOffCorner
from wop.core.tool_types.hand import ToolHand

from wop.core.blocks.base import BlockContext, Safety
from wop.core.blocks.grooving import GroovingBlock
from wop.core.blocks.turning_common import TurningSide
from wop.core.program_model.operations import LinearMove, Rapid, SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart
from wop.core.program_model.stock import stock_region


def standard(**values):
    return make_tool("groove", 1, replace(TOOL_TYPES.get("groove").default(), **values))


def corners(tool):
    return [(round(p.segment.start.x, 3), round(p.segment.start.z, 3)) for p in tool.shape.pieces]


class OutsideToolTests(unittest.TestCase):
    def test_the_default_is_a_blade_with_two_rounded_corners_on_a_long_holder(self):
        tool = standard()
        arcs = [isinstance(p.segment, ArcSegment) for p in tool.shape.pieces]
        self.assertEqual(arcs, [True, False, True, False, False, False, False, False, False])
        self.assertEqual([p.role.name[0] for p in tool.shape.pieces], list("CCCCHHHHC"))  # the blade is cutter, the holder is not
        self.assertEqual(tool.shape.pieces[0].segment.radius, 0.2)
        self.assertEqual(max(p.segment.end.x for p in tool.shape.pieces), 100)  # holder length 100 from the tip
        self.assertEqual(max(p.segment.end.z for p in tool.shape.pieces), 12)  # holder width 12, flush with the left side of the blade

    def test_the_touch_off_point_is_the_chosen_corner_at_the_front(self):
        left, right = standard(), standard(touch_off=TouchOffCorner.RIGHT)
        self.assertEqual((tip_of(left).x, tip_of(left).z), (0, 0))
        self.assertEqual((tip_of(right).x, tip_of(right).z), (0, 3))
        self.assertEqual(tip_of(with_tip_at_origin(right)).z, 0)


class InsideAndHandTests(unittest.TestCase):
    def test_the_inside_tool_points_outward_and_is_a_bar_along_z(self):
        tool = standard(inside=True)
        self.assertTrue(all(p.segment.end.x <= 1e-9 for p in tool.shape.pieces))  # the body lies towards the axis
        self.assertEqual(max(p.segment.end.z for p in tool.shape.pieces), 100)  # the length along Z from the left side of the blade
        self.assertEqual(min(p.segment.end.x for p in tool.shape.pieces), -22)  # blade reach 10 plus holder width 12

    def test_the_form_words_the_holder_for_the_side(self):
        definition = TOOL_TYPES.get("groove").default()
        self.assertEqual(definition.form_labels()["holder_width_mm"], "Holder width (across Z)")
        self.assertEqual(definition.form_labels()["holder_length_mm"], "Holder length (along X)")
        inside = replace(definition, inside=True).form_labels()
        self.assertEqual((inside["holder_width_mm"], inside["holder_length_mm"]), ("Holder width (along X)", "Holder length (along Z)"))

    def test_left_hand_is_the_mirror_image_in_z_outside_and_in_x_inside(self):
        right, left = standard(), standard(hand=ToolHand.LEFT)
        self.assertEqual([(x, -z + 0.0) for x, z in corners(right)], corners(left))
        right, left = standard(inside=True), standard(inside=True, hand=ToolHand.LEFT)
        self.assertEqual([(-x + 0.0, z) for x, z in corners(right)], corners(left))
        self.assertEqual(tip_of(left).z, tip_of(right).z)  # not mirrored in Z: left is still the smaller Z

    def test_left_means_the_smaller_z_for_either_hand(self):
        self.assertEqual(tip_of(standard(hand=ToolHand.LEFT)).z, -3)  # the corner at the smaller Z is the far one of the mirrored blade
        self.assertEqual(tip_of(standard(hand=ToolHand.LEFT, touch_off=TouchOffCorner.RIGHT)).z, 0)

    def test_a_left_hand_inside_tool_says_what_is_not_done(self):
        definition = replace(TOOL_TYPES.get("groove").default(), inside=True, hand=ToolHand.LEFT)
        self.assertIn("reversed", "\n".join(TOOL_TYPES.get("groove").info(definition)))


class FrontAngleTests(unittest.TestCase):
    def test_above_90_the_right_corner_is_deeper(self):
        front = standard(front_angle_deg=100, corner_radius_mm=0).shape.pieces[0].segment
        self.assertGreater(front.start.x, front.end.x)  # the front runs from the left corner (shallow) to the right corner (deeper)

    def test_below_90_the_left_corner_is_deeper(self):
        front = standard(front_angle_deg=80, corner_radius_mm=0).shape.pieces[0].segment
        self.assertLess(front.start.x, front.end.x)

    def test_the_tip_x_is_the_deepest_point(self):
        for angle in (80, 90, 100):
            tool = standard(front_angle_deg=angle)
            cutter = [p.segment.end.x for p in tool.shape.pieces if p.role is ToolSegmentRole.CUTTER]
            self.assertAlmostEqual(min(cutter), 0, delta=0.21)
            self.assertEqual(tip_of(tool).x, 0)


class RefusalTests(unittest.TestCase):
    def test_values_that_make_no_tool_are_refused(self):
        for values in ({"blade_width_mm": 0}, {"reach_mm": 0}, {"corner_radius_mm": 2}, {"front_angle_deg": 20},
                       {"holder_width_mm": 2}, {"holder_length_mm": 5}, {"inside": True, "holder_length_mm": 2},
                       {"reach_mm": 0.5, "front_angle_deg": 130}):
            with self.subTest(values=values), self.assertRaises(ToolError):
                standard(**values)


class EveryCombinationTests(unittest.TestCase):
    def test_every_combination_that_builds_is_a_valid_outline(self):
        import itertools

        built = 0
        for angle, radius, width, reach, inside, hand in itertools.product(
            (50, 90, 130), (0, 0.2, 1), (2, 3, 6), (3, 10), (False, True), (ToolHand.RIGHT, ToolHand.LEFT),
        ):
            try:
                tool = standard(front_angle_deg=angle, corner_radius_mm=radius, blade_width_mm=width, reach_mm=reach, inside=inside, hand=hand)
            except ToolError:
                continue
            built += 1
            self.assertTrue(is_valid_outline(tool.shape.segments), (angle, radius, width, reach, inside, hand))
        self.assertGreater(built, 50)


class PlannerTests(unittest.TestCase):
    """The planner works for the left side of the blade: a touch-off at the right corner moves every position by the blade width."""

    def plan(self, tool):
        raw = RawPart("steel", 30, 60)
        block = GroovingBlock(
            block_id="g", tool_number=1, spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, 800), side=TurningSide.OUTSIDE,
            start_z_mm=-10, width_mm=8, bottom_radius_mm=12, feed_mm_per_rev=0.05, finish_allowance_mm=0.2, finish_pass=True,
        )
        return block.generate(BlockContext(raw, with_tip_at_origin(tool), stock_region(raw), Safety(25, 10, 1)))

    def test_the_groove_is_the_same_with_either_touch_off_corner(self):
        left, right = self.plan(standard()), self.plan(standard(touch_off=TouchOffCorner.RIGHT))
        self.assertAlmostEqual(left.removed.area, right.removed.area, places=3)
        self.assertGreater(left.removed.area, 0)

        def moves(result):
            return [op.end for op in result.operations if isinstance(op, (Rapid, LinearMove))]

        plunges = 0
        for a, b in zip(moves(left), moves(right)):
            self.assertAlmostEqual(a.x, b.x, places=6)
            if a.z < 10:  # the safe point (Z 10) does not move
                self.assertAlmostEqual(b.z, a.z + 3, places=6)
                plunges += 1
        self.assertGreater(plunges, 4)

    def test_the_groove_is_the_same_for_a_left_hand_tool(self):
        base, mirrored = self.plan(standard()), self.plan(standard(hand=ToolHand.LEFT))
        self.assertAlmostEqual(base.removed.area, mirrored.removed.area, places=3)


if __name__ == "__main__":
    unittest.main()
