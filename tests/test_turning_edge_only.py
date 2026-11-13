"""A turning block with a start corner works on the edge of the part even when its target is the diameter of the bar or more, and a finishing
pass never ends by going into the material (a wall shorter than the nose radius is passed, not followed backwards)."""

import unittest

from tests.helpers import simple_tool
from tests.test_rough_follow import holder_cnmg  # a tool with a nose radius of 0.8 mm
from wop.core.blocks.base import BlockContext, Safety
from wop.core.blocks.turning import TurningBlock, TurningSide
from wop.core.contour import chamfer, fillet
from wop.core.geometry import LineSegment, Point
from wop.core.geometry.offset import offset_segments
from wop.core.program_model.operations import ArcMove, LinearMove, SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart
from wop.core.program_model.stock import stock_region

SAFETY = Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1)
SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
RAW = RawPart("steel", 30, 60)  # radius 15


def block(**overrides):
    values = dict(
        block_id="t", tool_number=1, spindle=SPINDLE, side=TurningSide.OUTSIDE, target_radius_mm=15, end_z_mm=-20,
        feed_mm_per_rev=0.2, depth_of_cut_mm=1, finish_allowance_mm=0.15, finish_pass=True, finish_feed_mm_per_rev=0.1,
    )
    values.update(overrides)
    return TurningBlock(**values)


def plan(turning, tool=None):
    return turning.generate(BlockContext(RAW, tool or simple_tool(1), stock_region(RAW), SAFETY))


class EdgeOnlyTests(unittest.TestCase):
    def test_a_start_corner_cuts_the_edge_when_the_target_is_the_diameter_of_the_bar(self):
        for corner, area in ((chamfer(1), 0.5), (fillet(2), 4 * (1 - 3.141592653589793 / 4))):
            result = plan(block(start_corner=corner))
            self.assertNotIn("already at or beyond", " ".join(result.messages))
            self.assertAlmostEqual(result.removed.area, area, delta=0.05)
            self.assertTrue(any(isinstance(op, (LinearMove, ArcMove)) for op in result.operations))

    def test_it_also_works_with_a_target_larger_than_the_bar(self):
        result = plan(block(target_radius_mm=15.5, start_corner=chamfer(1)))
        self.assertGreater(result.removed.area, 0.05)
        self.assertNotIn("already at or beyond", " ".join(result.messages))

    def test_a_corner_that_cuts_nothing_says_so(self):
        result = plan(block(target_radius_mm=20, start_corner=chamfer(1)))
        self.assertIn("already at or beyond the target radius", " ".join(result.messages))
        self.assertEqual(result.removed.area, 0)
        self.assertFalse(any(isinstance(op, (LinearMove, ArcMove)) for op in result.operations))

    def test_without_a_corner_the_old_note_stays(self):
        result = plan(block())
        self.assertIn("already at or beyond the target radius", " ".join(result.messages))


class LastMoveTests(unittest.TestCase):
    def assert_ends_going_away(self, result, target):
        """From where the finishing pass has reached the end Z of the contour on, the radius never gets smaller: the tool does not go back into the part."""
        feeds = [op for op in result.operations if isinstance(op, (LinearMove, ArcMove))]
        lowest_z = min(op.end.z for op in feeds)
        at_end = next(i for i, op in enumerate(feeds) if op.end.z <= lowest_z + 1e-6)
        for before, after in zip(feeds[at_end:], feeds[at_end + 1:]):
            self.assertGreaterEqual(after.end.x, before.end.x - 1e-6, (target, before.end, after.end))

    def test_the_finishing_pass_does_not_end_by_going_into_the_material(self):
        for target in (14.995, 14.9, 14.5):  # the shoulder is lower than the nose radius (0.8 mm)
            result = plan(block(target_radius_mm=target, start_corner=fillet(2)), holder_cnmg())
            self.assert_ends_going_away(result, target)

    def test_a_contour_block_whose_contour_ends_just_inside_the_material_ends_away_from_it_too(self):
        from tests.test_blocks_turning_contour import block as contour_block, context as contour_context, contour_of

        for end_radius in (14.995, 14.9):
            shape = contour_of((12, 0), (end_radius, -2), (end_radius, -20))
            result = contour_block(shape, finish_allowance_mm=0.15, finish_pass=True, finish_feed_mm_per_rev=0.1).generate(contour_context(shape, tool=holder_cnmg()))
            self.assert_ends_going_away(result, end_radius)

    def test_a_wall_lower_than_the_nose_radius_is_passed_not_followed_backwards(self):
        cylinder = LineSegment(Point(14.9, -2), Point(14.9, -20))
        wall = LineSegment(Point(14.9, -20), Point(15, -20))
        moved = offset_segments([(0, cylinder), (1, wall)], -0.3, closed=False)
        self.assertEqual([index for index, _segment in moved], [0])  # the wall is gone from the path
        self.assertTrue(moved[0][1].end.is_close(Point(15.2, -19.7), 1e-9))  # the centre stops where the offset of the wall would be

    def test_a_wall_in_the_middle_is_left_out_and_its_neighbours_meet(self):
        first = LineSegment(Point(14.9, -2), Point(14.9, -20))
        wall = LineSegment(Point(14.9, -20), Point(15, -20))
        after = LineSegment(Point(15, -20), Point(15, -30))
        moved = offset_segments([(0, first), (1, wall), (2, after)], -0.3, closed=False)
        self.assertNotIn(1, [index for index, _segment in moved])
        for (_i, a), (_j, b) in zip(moved, moved[1:]):
            self.assertTrue(a.end.is_close(b.start, 1e-6), (a, b))  # a connected path

    def test_a_wall_higher_than_the_nose_radius_is_still_followed(self):
        cylinder = LineSegment(Point(14.0, -2), Point(14.0, -20))
        wall = LineSegment(Point(14.0, -20), Point(15, -20))
        moved = offset_segments([(0, cylinder), (1, wall)], -0.3, closed=False)
        self.assertEqual([index for index, _segment in moved], [0, 1])


if __name__ == "__main__":
    unittest.main()
