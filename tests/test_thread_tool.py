import math
import unittest
from dataclasses import replace

from tests.helpers import is_valid_outline
from wop.core.geometry import ArcSegment, LineSegment
from wop.core.tooling.tool import ToolError, ToolSegmentRole, flank_angles_by_side, flank_reach_by_side
from wop.core.tooling.tool_reference import tip_of, with_tip_at_origin
from wop.core.tool_types import TOOL_TYPES, make_tool
from wop.core.tool_types.hand import ToolHand


def standard(**values):
    return make_tool("thread", 1, replace(TOOL_TYPES.get("thread").default(), **values))


def pieces(tool, kind):
    return [p for p in tool.shape.pieces if isinstance(p.segment, kind)]


class PointedToolTests(unittest.TestCase):
    def test_the_default_is_a_60_degree_point_with_a_small_radius_on_a_long_body(self):
        tool = standard()
        self.assertEqual(len(pieces(tool, ArcSegment)), 1)
        self.assertAlmostEqual(pieces(tool, ArcSegment)[0].segment.radius, 0.1)
        self.assertEqual([p.role.name[0] for p in tool.shape.pieces], list("CCCHHHHH"))  # two flanks and the nose cut
        self.assertEqual(max(p.segment.end.x for p in tool.shape.pieces), 100)  # length from the point
        self.assertEqual(max(p.segment.end.z for p in tool.shape.pieces), 6)  # width 12, the point in the middle
        self.assertEqual(min(p.segment.end.z for p in tool.shape.pieces), -6)

    def test_the_flanks_are_30_degrees_from_the_radial_direction(self):
        low, high = flank_angles_by_side(with_tip_at_origin(standard()).shape)
        self.assertAlmostEqual(low, 30, places=3)
        self.assertAlmostEqual(high, 30, places=3)

    def test_the_touch_off_point_is_the_lowest_point_of_the_nose(self):
        tip = tip_of(standard())
        self.assertEqual((tip.x, tip.z), (0, 0))
        cutter = [p.segment.end.x for p in standard().shape.pieces if p.role is ToolSegmentRole.CUTTER]
        self.assertAlmostEqual(min(cutter), 0.05, delta=0.06)  # the arc reaches down to x = 0


class AsymmetricTests(unittest.TestCase):
    def test_the_lead_angle_is_the_flank_on_the_smaller_z_side(self):
        tool = with_tip_at_origin(standard(lead_angle_deg=3))  # a buttress-like tool: 3 degrees leading, 57 trailing
        low, high = flank_angles_by_side(tool.shape)
        self.assertAlmostEqual(low, 3, places=3)
        self.assertAlmostEqual(high, 57, places=3)

    def test_a_flank_straight_along_x_has_the_angle_0(self):
        tool = with_tip_at_origin(standard(included_angle_deg=30, lead_angle_deg=0, nose_radius_mm=0))
        self.assertAlmostEqual(flank_angles_by_side(tool.shape)[0], 0, places=3)
        self.assertAlmostEqual(flank_reach_by_side(tool.shape, 2)[0], 0, places=3)

    def test_the_lead_angle_follows_the_included_angle_while_the_tool_is_symmetric(self):
        kind = TOOL_TYPES.get("thread")
        default = kind.default()
        self.assertEqual(kind.reconcile(default, replace(default, included_angle_deg=55)).lead_angle_deg, 27.5)
        apart = replace(default, lead_angle_deg=3)
        self.assertEqual(kind.reconcile(apart, replace(apart, included_angle_deg=55)).lead_angle_deg, 3)

    def test_the_reach_of_a_rounded_tip_is_a_little_more_than_a_sharp_v(self):
        sharp = with_tip_at_origin(standard(nose_radius_mm=0))
        rounded = with_tip_at_origin(standard(nose_radius_mm=0.2))
        depth = 1.5
        self.assertAlmostEqual(flank_reach_by_side(sharp.shape, depth)[0], depth * math.tan(math.radians(30)), places=4)
        self.assertGreater(flank_reach_by_side(rounded.shape, depth)[0], depth * math.tan(math.radians(30)))


class FlatTests(unittest.TestCase):
    def test_a_flat_without_radius_has_sharp_corners_and_the_touch_off_point_in_its_middle(self):
        tool = standard(flat_mm=1, nose_radius_mm=0)
        self.assertEqual(pieces(tool, ArcSegment), [])
        flat = [p.segment for p in pieces(tool, LineSegment) if abs(p.segment.start.x) < 1e-9 and abs(p.segment.end.x) < 1e-9]
        self.assertAlmostEqual(abs(flat[0].end.z - flat[0].start.z), 1)
        self.assertAlmostEqual(tip_of(tool).z, 0)

    def test_flat_and_radius_combine_and_the_roundings_take_their_tangent_length(self):
        tool = standard(flat_mm=1, nose_radius_mm=0.2)
        self.assertEqual(len(pieces(tool, ArcSegment)), 2)
        flat = [p.segment for p in pieces(tool, LineSegment) if abs(p.segment.start.x) < 1e-9 and abs(p.segment.end.x) < 1e-9][0]
        tangent = 0.2 / math.tan(math.radians(120) / 2)  # a 120 degree corner
        self.assertAlmostEqual(abs(flat.end.z - flat.start.z), 1 - 2 * tangent, places=4)

    def test_a_radius_that_does_not_fit_the_flat_is_refused_with_a_message(self):
        with self.assertRaises(ToolError) as caught:
            standard(flat_mm=1, nose_radius_mm=0.9)
        self.assertIn("too big for the flat", str(caught.exception))
        standard(flat_mm=1, nose_radius_mm=0.6)  # a 120 degree corner has a tangent length of 0.58 of the radius: this fits
        self.assertIn("too big for the flat", "\n".join(TOOL_TYPES.get("thread").info(replace(TOOL_TYPES.get("thread").default(), flat_mm=1, nose_radius_mm=0.9))))


class BodyTests(unittest.TestCase):
    def test_the_point_can_be_off_centre(self):
        tool = standard(tip_distance_mm=3)
        zs = [p.segment.end.z for p in tool.shape.pieces]
        self.assertEqual((min(zs), max(zs)), (-3, 9))

    def test_a_low_cutting_height_steps_out_to_the_body_at_a_right_angle_to_x(self):
        tool = standard(cutting_height_mm=1)
        holder = [p.segment for p in tool.shape.pieces if p.role is ToolSegmentRole.HOLDER]
        step = [s for s in holder if abs(s.start.x - 1) < 1e-6 and abs(s.end.x - 1) < 1e-6]
        self.assertEqual(len(step), 2)  # one on each side

    def test_a_big_cutting_height_lets_the_flanks_run_to_the_body(self):
        tool = standard(cutting_height_mm=50)
        flanks = [p.segment for p in tool.shape.pieces if p.role is ToolSegmentRole.CUTTER and isinstance(p.segment, LineSegment)]
        self.assertEqual(sorted(round(abs(s.end.z) if abs(s.end.z) > 5 else abs(s.start.z), 3) for s in flanks), [6, 6])
        self.assertEqual([p.role.name[0] for p in tool.shape.pieces], list("CCCHHH"))  # no steps

    def test_a_point_outside_the_body_is_refused(self):
        with self.assertRaises(ToolError):
            standard(tip_distance_mm=0.05)
        with self.assertRaises(ToolError):
            standard(width_mm=5, tip_distance_mm=6)


class InsideAndHandTests(unittest.TestCase):
    def test_the_inside_tool_is_a_bar_along_z_with_the_point_standing_out(self):
        tool = standard(inside=True, cutting_height_mm=3)
        xs = [p.segment.end.x for p in tool.shape.pieces]
        zs = [p.segment.end.z for p in tool.shape.pieces]
        self.assertTrue(max(xs) <= 1e-9)
        self.assertEqual(min(xs), -15)  # cutting height 3 plus the bar width 12
        self.assertEqual((min(zs), max(zs)), (-6, 94))  # the length 100 along Z from the left side of the bar

    def test_a_point_that_stands_out_over_the_end_of_the_bar_is_refused(self):
        with self.assertRaises(ToolError):
            standard(inside=True, cutting_height_mm=20)

    def test_left_hand_is_a_mirror_in_z_outside_and_in_x_inside(self):
        def corners(tool):
            return [(round(p.segment.start.x, 3), round(p.segment.start.z, 3)) for p in tool.shape.pieces]

        right, left = standard(), standard(hand=ToolHand.LEFT)
        self.assertEqual([(x, -z + 0.0) for x, z in corners(right)], corners(left))
        right, left = standard(inside=True, cutting_height_mm=3), standard(inside=True, cutting_height_mm=3, hand=ToolHand.LEFT)
        self.assertEqual([(-x + 0.0, z) for x, z in corners(right)], corners(left))

    def test_the_form_words_width_and_length_for_the_side(self):
        definition = TOOL_TYPES.get("thread").default()
        self.assertEqual(definition.form_labels()["width_mm"], "Width (across Z)")
        inside = replace(definition, inside=True).form_labels()
        self.assertEqual((inside["width_mm"], inside["length_mm"]), ("Width (along X)", "Length (along Z)"))


class EveryCombinationTests(unittest.TestCase):
    def test_every_combination_that_builds_is_a_valid_outline(self):
        import itertools

        built = 0
        for included, lead, radius, flat, height, inside, hand in itertools.product(
            (30, 60, 100), (0, 10, 0.5), (0, 0.1, 0.5), (0, 1), (2, 6, 50), (False, True), (ToolHand.RIGHT, ToolHand.LEFT),
        ):
            lead_deg = lead * included if lead < 1 else lead
            try:
                tool = standard(included_angle_deg=included, lead_angle_deg=lead_deg, nose_radius_mm=radius, flat_mm=flat,
                                cutting_height_mm=height, inside=inside, hand=hand)
            except ToolError:
                continue
            built += 1
            self.assertTrue(is_valid_outline(tool.shape.segments), (included, lead_deg, radius, flat, height, inside, hand))
        self.assertGreater(built, 100)


if __name__ == "__main__":
    unittest.main()
