import unittest

from tests.helpers import simple_tool
from wop.core.program_model.operations import (
    BlockBegin,
    BlockEnd,
    LinearMove,
    Rapid,
    SpindleMode,
    SpindleSetting,
)
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks.base import BlockContext, BlockError, Safety
from wop.core.blocks.facing import FacingBlock, FacingDirection
from wop.core.program_model.stock import stock_region

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
SAFETY = Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1)


def make_block(**overrides) -> "FacingBlock":
    values = dict(
        block_id="f1", tool_number=1, spindle=SPINDLE, target_z_mm=-1,
        feed_mm_per_rev=0.2, depth_of_cut_mm=1,
    )
    values.update(overrides)
    return FacingBlock(**values)


def context_for(raw_part: RawPart) -> "BlockContext":
    return BlockContext(raw_part, simple_tool(1), stock_region(raw_part), SAFETY)


def feed_moves(result):
    """The cutting feeds across the face: longer than the clearance at one Z (not the feed through the last clearance into the material,
    X12, nor the feeds up out of it)."""
    moves = [op for op in result.operations if isinstance(op, (Rapid, LinearMove))]
    return [
        op for before, op in zip(moves, moves[1:])
        if isinstance(op, LinearMove) and abs(op.end.z - before.end.z) < 1e-9 and abs(op.end.x - before.end.x) > SAFETY.clearance_mm + 1e-9
    ]


def path(result):
    """The moves of the block as ("R" or "F", x, z), without the markers."""
    return [("R" if isinstance(op, Rapid) else "F", op.end.x, op.end.z) for op in result.operations if isinstance(op, (Rapid, LinearMove))]


class FacingTests(unittest.TestCase):
    def setUp(self):
        self.context = context_for(RawPart("steel", 30, 60))

    def test_removes_the_material_above_the_target(self):
        result = make_block().generate(self.context)
        self.assertAlmostEqual(result.removed.area, 15 * 1)
        left = self.context.residual.difference(result.removed)
        self.assertAlmostEqual(left.bounds.max_z, -1)

    def test_a_finishing_allowance_as_big_as_the_whole_face_still_plans(self):
        """The roughing makes no move, the finishing pass starts from nowhere (it used to fail on a missing position)."""
        result = make_block(finish_allowance_mm=1_000_000, finish_pass=True).generate(context_for(RawPart("steel", 30, 60)))
        self.assertTrue(any(isinstance(op, LinearMove) for op in result.operations))

    def test_block_markers_wrap_the_operations(self):
        operations = make_block().generate(self.context).operations
        self.assertIsInstance(operations[0], BlockBegin)
        self.assertIsInstance(operations[-1], BlockEnd)

    def test_single_pass_without_allowance(self):
        moves = feed_moves(make_block().generate(self.context))
        self.assertEqual([(m.end.x, m.end.z) for m in moves], [(0, -1)])

    def test_allowance_adds_roughing_passes_and_a_finishing_pass(self):
        block = make_block(depth_of_cut_mm=0.5, finish_allowance_mm=0.2, finish_pass=True, finish_feed_mm_per_rev=0.1)
        moves = feed_moves(block.generate(self.context))
        self.assertEqual([round(m.end.z, 6) for m in moves], [-0.4, -0.8, -1.0])
        self.assertEqual([m.feed_mm_per_rev for m in moves], [0.2, 0.2, 0.1])

    def test_an_allowance_without_the_finishing_pass_is_left_on_the_face(self):
        block = make_block(depth_of_cut_mm=0.5, finish_allowance_mm=0.2, finish_feed_mm_per_rev=0.1)
        moves = feed_moves(block.generate(self.context))
        self.assertEqual([round(m.end.z, 6) for m in moves], [-0.4, -0.8])
        self.assertAlmostEqual(self.context.residual.difference(block.generate(self.context).removed).bounds.max_z, -0.8)

    def test_outside_in_runs_down_across_and_back_in_one_rapid(self):
        steps = [(kind, round(x, 6), round(z, 6)) for kind, x, z in path(make_block(depth_of_cut_mm=0.5).generate(self.context))]
        self.assertEqual(steps, [
            ("R", 25, 1),  # the safe radius, one clearance above the top (Z0)
            ("R", 16, -0.5), ("F", 15, -0.5), ("F", 0, -0.5),  # beside the part (radius 15 + 1), the last clearance at feed (X12), across
            ("F", 0, 0.51), ("R", 16, 0.51),  # up out of the clearance at feed, back in a rapid
            ("R", 16, -1), ("F", 15, -1), ("F", 0, -1), ("F", 0, 0.01),
            ("R", 25, 10),  # one rapid to the safe radius and safe Z
        ])

    def test_a_finishing_speed_is_set_before_the_finishing_pass_only(self):
        from wop.core.program_model.operations import SetSpindle
        result = make_block(depth_of_cut_mm=0.5, finish_pass=True, finish_spindle_value=2000).generate(self.context)
        ops = result.operations
        changes = [i for i, op in enumerate(ops) if isinstance(op, SetSpindle)]
        self.assertEqual(len(changes), 1)
        self.assertEqual(ops[changes[0]].setting.value, 2000)
        feeds_after = [op for op in ops[changes[0]:] if isinstance(op, LinearMove)]
        self.assertEqual({op.end.z for op in feeds_after if op.end.z <= 0}, {-1})  # the finishing pass at the target (then up above the top at feed, X12)
        self.assertEqual([op for op in make_block(finish_spindle_value=2000).generate(self.context).operations if isinstance(op, SetSpindle)], [])

    def test_centre_out_runs_down_past_the_centre_and_out(self):
        steps = path(make_block(direction=FacingDirection.CENTER_OUT, overtravel_mm=0.8).generate(self.context))
        self.assertEqual(steps, [("R", 25, 1), ("R", -0.8, 1), ("F", -0.8, -1), ("F", 16, -1), ("R", 25, 10)])  # beside the part: a rapid away

    def test_centre_out_rises_at_feed_off_each_face(self):
        steps = path(make_block(direction=FacingDirection.CENTER_OUT, overtravel_mm=0.8, depth_of_cut_mm=0.5).generate(self.context))
        self.assertEqual(steps, [
            ("R", 25, 1), ("R", -0.8, 1), ("F", -0.8, -0.5), ("F", 16, -0.5),
            ("F", 16, 0.5), ("R", 16, 1), ("R", -0.8, 1), ("F", -0.8, -1), ("F", 16, -1),  # the first clearance off the face at feed (X12), over the top
            ("R", 25, 10),
        ])

    def test_the_overtravel_goes_past_the_centre(self):
        moves = feed_moves(make_block(overtravel_mm=0.8).generate(self.context))
        self.assertEqual([m.end.x for m in moves], [-0.8])

    def test_passes_start_outside_the_material(self):
        result = make_block().generate(self.context)
        first_feed = next(i for i, op in enumerate(result.operations) if isinstance(op, LinearMove))
        rapid_to_pass = [op for op in result.operations[:first_feed] if isinstance(op, Rapid)][-1]
        self.assertEqual(rapid_to_pass.end.x, 16)  # radius 15 + clearance 1

    def test_centre_out_removes_the_same_material(self):
        outside_in = make_block().generate(self.context)
        centre_out = make_block(direction=FacingDirection.CENTER_OUT).generate(self.context)
        self.assertAlmostEqual(centre_out.removed.area, outside_in.removed.area)
        moves = feed_moves(centre_out)
        self.assertEqual([m.end.x for m in moves], [15 + 1])

    def test_tube_is_faced_from_the_outer_to_the_inner_radius(self):
        context = context_for(RawPart("steel", 30, 60, inner_diameter_mm=10))
        result = make_block().generate(context)
        self.assertAlmostEqual(result.removed.area, (15 - 5) * 1)
        self.assertAlmostEqual(feed_moves(result)[0].end.x, 5)  # stops at the bore

    def test_nothing_to_cut_above_the_target(self):
        result = make_block(target_z_mm=0).generate(self.context)
        self.assertTrue(result.removed.is_empty)
        self.assertEqual(len(result.operations), 2)
        self.assertEqual(len(result.messages), 1)

    def test_invalid_parameters_are_rejected(self):
        for overrides in (
            dict(feed_mm_per_rev=0),
            dict(depth_of_cut_mm=-1),
            dict(finish_allowance_mm=-0.1),
            dict(finish_feed_mm_per_rev=0),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(BlockError):
                    make_block(**overrides)


if __name__ == "__main__":
    unittest.main()
