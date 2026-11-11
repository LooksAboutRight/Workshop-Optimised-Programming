import math
import unittest

from tests.helpers import simple_tool
from wop.core.contour import chamfer, fillet
from wop.core.geometry import Point
from wop.core.program_model.operations import ArcMove, LinearMove, Rapid, SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks.base import BlockContext, BlockError, Safety
from wop.core.blocks.turning import PassDirection, TurningBlock, TurningSide
from wop.core.geometry.region import Region
from wop.core.program_model.stock import stock_region
SAFETY = Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1)

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
ROUGH_FEED = 0.25
FINISH_FEED = 0.1
AREA_TOLERANCE = 0.02


def make_block(**overrides) -> "TurningBlock":
    values = dict(
        block_id="t1", tool_number=1, spindle=SPINDLE, side=TurningSide.OUTSIDE,
        target_radius_mm=10, end_z_mm=-30,
        feed_mm_per_rev=ROUGH_FEED, depth_of_cut_mm=2,
    )
    values.update(overrides)
    return TurningBlock(**values)


def context_for(raw_part: RawPart) -> "BlockContext":
    return BlockContext(raw_part, simple_tool(1), stock_region(raw_part), SAFETY)


def moves_with_feed(result, feed):
    return [
        op for op in result.operations
        if isinstance(op, (LinearMove, ArcMove)) and op.feed_mm_per_rev == feed
    ]


class OutsideTurningTests(unittest.TestCase):
    def setUp(self):
        self.context = context_for(RawPart("steel", 30, 60))

    def test_removes_the_ring_around_the_cylinder(self):
        result = make_block().generate(self.context)
        self.assertAlmostEqual(result.removed.area, (15 - 10) * 30, delta=AREA_TOLERANCE)

    def test_both_pass_directions_remove_the_same_material(self):
        along_z = make_block().generate(self.context)
        along_x = make_block(pass_direction=PassDirection.ALONG_X).generate(self.context)
        self.assertAlmostEqual(along_z.removed.area, along_x.removed.area, delta=AREA_TOLERANCE)

    def test_chamfer_on_the_start_edge_removes_a_little_more(self):
        result = make_block(start_corner=chamfer(1)).generate(self.context)
        self.assertAlmostEqual(result.removed.area, 5 * 30 + 0.5, delta=AREA_TOLERANCE)

    def test_radius_in_the_shoulder_corner_leaves_material(self):
        radius = 1.5
        result = make_block(shoulder_corner=fillet(radius)).generate(self.context)
        left_behind = (1 - math.pi / 4) * radius**2
        self.assertAlmostEqual(result.removed.area, 5 * 30 - left_behind, delta=AREA_TOLERANCE)

    def test_finishing_pass_follows_the_outline_with_chamfer_and_arc(self):
        block = make_block(
            start_corner=chamfer(1), shoulder_corner=fillet(1.5), finish_feed_mm_per_rev=FINISH_FEED
        )
        finish = moves_with_feed(block.generate(self.context), FINISH_FEED)
        arcs = [m for m in finish if isinstance(m, ArcMove)]
        self.assertEqual(len(arcs), 1)
        self.assertEqual(finish[0].end, Point(10 - 1, 0))  # approach to the chamfer start (the front face)
        self.assertTrue(finish[1].end.is_close(Point(10, -1)))  # the chamfer
        shoulder = next(i for i, move in enumerate(finish) if move.end == Point(15, -30))  # up the shoulder to the stock
        self.assertTrue(all(abs(move.end.z - (-30)) < 1e-9 or abs(move.end.x - 15) < 1e-9 for move in finish[shoulder + 1:]))  # then straight out of the clearance at feed (X12)

    def test_roughing_keeps_the_finishing_allowance(self):
        block = make_block(finish_allowance_mm=0.3, finish_feed_mm_per_rev=FINISH_FEED)
        rough = moves_with_feed(block.generate(self.context), ROUGH_FEED)
        self.assertTrue(rough)
        for move in rough:
            self.assertGreaterEqual(move.end.x, 10.3 - 1e-9)
            self.assertGreaterEqual(move.end.z, -29.7 - 1e-9)

    def test_transverse_roughing_keeps_the_allowance_too(self):
        block = make_block(
            pass_direction=PassDirection.ALONG_X, finish_allowance_mm=0.3,
            finish_feed_mm_per_rev=FINISH_FEED,
        )
        rough = moves_with_feed(block.generate(self.context), ROUGH_FEED)
        self.assertTrue(rough)
        for move in rough:  # the lines end on the allowance; the feeds in and up out of the clearance (X12) stay outside it
            self.assertGreaterEqual(move.end.x, 10.3 - 1e-9)
            self.assertGreaterEqual(move.end.z, -29.7 - 1e-9)
        self.assertAlmostEqual(min(move.end.x for move in rough), 10.3)

    def test_passes_are_not_deeper_than_the_depth_of_cut(self):
        rough = moves_with_feed(make_block().generate(self.context), ROUGH_FEED)
        radii = sorted({round(m.end.x, 6) for m in rough}, reverse=True)
        steps = [a - b for a, b in zip([15] + radii, radii)]
        self.assertTrue(all(step <= 2 + 1e-6 for step in steps))
        self.assertAlmostEqual(radii[-1], 10)

    def test_approach_at_the_front_face_is_not_a_plunge(self):
        # z_approach lies exactly on the face of the raw part: air, so no feed move there.
        block = make_block(finish_allowance_mm=0.3, finish_feed_mm_per_rev=FINISH_FEED)
        for move in moves_with_feed(block.generate(self.context), ROUGH_FEED):
            self.assertNotEqual(move.end.z, SAFETY.clearance_mm)

    def test_end_position_in_front_of_the_material_gives_a_message(self):
        result = make_block(end_z_mm=5).generate(self.context)
        self.assertTrue(result.removed.is_empty)
        self.assertEqual(len(result.messages), 1)

    def test_nothing_to_do_if_already_at_the_radius(self):
        result = make_block(target_radius_mm=15).generate(self.context)
        self.assertTrue(result.removed.is_empty)
        self.assertEqual(len(result.messages), 1)

    def test_corner_too_large_is_reported_as_a_block_error(self):
        with self.assertRaises(BlockError):
            make_block(shoulder_corner=fillet(20)).generate(self.context)


class InsideTurningTests(unittest.TestCase):
    """With a boring bar (`simple_tool(1, side=-1)`: its body towards the axis, 8 mm wide, so it fits the bore of 14 mm with the far wall
    of the bore in mind)."""

    def setUp(self):
        raw_part = RawPart("steel", 40, 50, inner_diameter_mm=14)
        self.context = BlockContext(raw_part, simple_tool(1, side=-1), stock_region(raw_part), SAFETY)

    def block(self, **overrides):
        values = dict(side=TurningSide.INSIDE, target_radius_mm=10, end_z_mm=-25)
        values.update(overrides)
        return make_block(**values)

    def test_bore_removes_the_ring_inside_the_radius(self):
        result = self.block().generate(self.context)
        self.assertAlmostEqual(result.removed.area, (10 - 7) * 25, delta=AREA_TOLERANCE)

    def test_both_pass_directions_remove_the_same_material(self):
        along_z = self.block().generate(self.context)
        along_x = self.block(pass_direction=PassDirection.ALONG_X).generate(self.context)
        self.assertAlmostEqual(along_z.removed.area, along_x.removed.area, delta=AREA_TOLERANCE)

    def test_passes_move_outwards_and_stay_inside_the_target(self):
        block = self.block(finish_allowance_mm=0.2, finish_feed_mm_per_rev=FINISH_FEED)
        operations = block.generate(self.context).operations
        rough = [  # the roughing lines along Z (not a move along the contour back to the line before, nor the clearance in and out at feed, X12)
            op for before, op in zip(operations, operations[1:])
            if isinstance(op, LinearMove) and op.feed_mm_per_rev == ROUGH_FEED and abs(op.end.x - before.end.x) < 1e-9
            and abs(op.end.z - before.end.z) > SAFETY.clearance_mm + 0.05
        ]
        radii = [round(m.end.x, 6) for m in rough]
        self.assertEqual(radii, sorted(radii))
        self.assertLessEqual(max(radii), 9.8 + 1e-9)
        self.assertGreater(min(radii), 7)

    def test_the_bore_is_reached_one_clearance_in_front_of_the_face(self):
        # the same start as outside (the user, 2026-10-23: one clearance away is fine and needs no rule of its own)
        result = self.block().generate(self.context)
        first, second = [op for op in result.operations if hasattr(op, "end")][:2]
        self.assertIsInstance(first, Rapid)
        self.assertAlmostEqual(first.end.z, SAFETY.clearance_mm)
        self.assertLess(first.end.x, 10)  # over the bore
        self.assertIsInstance(second, LinearMove)  # the last clearance into the material at feed (X12)
        self.assertEqual(second.end.x, first.end.x)

    def test_a_solid_part_is_planned_from_the_axis(self):
        context = BlockContext(RawPart("steel", 40, 50), simple_tool(1, side=-1), stock_region(RawPart("steel", 40, 50)), SAFETY)
        result = self.block().generate(context)  # the collision checks tell whether the tool can do it
        self.assertFalse(result.removed.is_empty)
        # the bottom is cut a little past the axis, as a face (no pip); the far half of the bar is in the checks
        self.assertGreaterEqual(min(op.end.x for op in result.operations if hasattr(op, "end")), -2 * SAFETY.clearance_mm - 1e-9)

    def blind_hole_context(self, depth_mm):
        raw_part = RawPart("steel", 40, 50)
        residual = stock_region(raw_part).difference(Region.rectangle(0, -depth_mm, 7, 0))
        return BlockContext(raw_part, simple_tool(1, side=-1), residual, SAFETY)

    def test_blind_hole_deep_enough_can_be_bored(self):
        result = self.block().generate(self.blind_hole_context(30))
        self.assertAlmostEqual(result.removed.area, (10 - 7) * 25, delta=AREA_TOLERANCE)

    def test_blind_hole_too_short_leaves_the_core_to_the_collision_checks(self):
        result = self.block().generate(self.blind_hole_context(15))
        self.assertFalse(result.removed.is_empty)  # the bottom of the hole is cut; no "needs a hole" stop any more


class ValidationTests(unittest.TestCase):
    def test_invalid_parameters_are_rejected(self):
        for overrides in (
            dict(target_radius_mm=0),
            dict(feed_mm_per_rev=0),
            dict(depth_of_cut_mm=0),
            dict(finish_allowance_mm=-1),
            dict(finish_feed_mm_per_rev=-1),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(BlockError):
                    make_block(**overrides)


class TaperTests(unittest.TestCase):
    """The taper: its included angle; 0 straight, positive larger towards the chuck, the target radius at Z 0."""

    def setUp(self):
        self.context = context_for(RawPart("steel", 30, 60))

    def test_zero_is_the_cylinder(self):
        self.assertAlmostEqual(make_block(taper_deg=0).radius_at(-30), 10)

    def test_a_positive_angle_is_larger_towards_the_chuck(self):
        block = make_block(taper_deg=10)
        self.assertAlmostEqual(block.radius_at(0), 10)
        self.assertAlmostEqual(block.radius_at(-30), 10 + 30 * math.tan(math.radians(5)))
        line = block.target_outline(self.context)[0]
        self.assertAlmostEqual(line.start.x, 10)
        self.assertAlmostEqual(line.end.x, block.radius_at(-30))

    def test_the_cone_is_cut_as_drawn(self):
        block = make_block(taper_deg=-10)
        result = block.generate(self.context)
        cone = (15 - (10 + block.radius_at(-30)) / 2) * 30  # the ring between the stock and the cone
        self.assertAlmostEqual(result.removed.area, cone, delta=AREA_TOLERANCE)

    def test_a_cone_that_leaves_the_stock_has_no_shoulder(self):
        block = make_block(taper_deg=30)  # 10 + 30 tan 15 = 18 mm at the end: beyond the stock radius 15
        outline = block.target_outline(self.context)
        self.assertEqual(len(outline), 1)
        self.assertGreater(outline[0].end.x, 15)

    def test_a_cone_through_the_axis_is_refused(self):
        with self.assertRaises(BlockError):
            make_block(taper_deg=-60).generate(self.context)

    def test_the_angle_must_be_below_a_straight_angle(self):
        for angle in (180, -180):
            with self.subTest(angle), self.assertRaises(BlockError):
                make_block(taper_deg=angle)


if __name__ == "__main__":
    unittest.main()
