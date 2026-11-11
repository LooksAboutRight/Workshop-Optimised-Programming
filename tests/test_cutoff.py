import unittest

from wop.core.program_model.operations import SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks.grooving import GroovingBlock
from wop.core.blocks.base import Safety
from wop.core.blocks.turning_common import TurningSide
from wop.core.program_model.cutoff import split_off
from wop.core.program_model.program import Program, plan_program
from wop.core.geometry.region import Region
from wop.core.tooling.tool_presets import groove_tool


class SplitOffTests(unittest.TestCase):
    def test_one_piece_stays_as_it_is(self):
        part = Region.rectangle(0, -20, 10, 0)
        kept, dropped = split_off(part)
        self.assertTrue(dropped.is_empty)
        self.assertAlmostEqual(kept.area, part.area, delta=0.05)

    def test_the_piece_at_the_chuck_end_is_kept(self):
        both = Region.rectangle(0, -20, 10, -12).union(Region.rectangle(0, -10, 10, 0))
        kept, dropped = split_off(both)
        self.assertAlmostEqual(kept.bounds.min_z, -20, delta=0.1)
        self.assertAlmostEqual(dropped.bounds.max_z, 0, delta=0.1)

    def test_when_both_reach_the_chuck_end_the_grip_decides(self):
        ring_and_core = Region.rectangle(0, -20, 4, 0).union(Region.rectangle(8, -20, 12, 0))
        kept, _dropped = split_off(ring_and_core)  # no workholding / outside grip: the outer piece
        self.assertGreater(kept.bounds.min_x, 7)
        kept, _dropped = split_off(ring_and_core, grip_inside=True)  # held in the bore: the inner piece
        self.assertLess(kept.bounds.max_x, 5)


class PartOffTests(unittest.TestCase):
    def _program(self, **overrides):
        values = dict(
            block_id="g1", tool_number=1, spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, 800),
            side=TurningSide.OUTSIDE, start_z_mm=-30, width_mm=4, bottom_radius_mm=0, feed_mm_per_rev=0.05,
        )
        values.update(overrides)
        return Program(
            raw_part=RawPart("steel", 16, 60), tools=(groove_tool(1, "groove 3"),),
            safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1),
            blocks=(GroovingBlock(**values),),
        )

    def test_a_groove_to_the_axis_cuts_the_part_off(self):
        plan = plan_program(self._program())
        block = plan.blocks[0]
        self.assertFalse(block.cut_off.is_empty)
        self.assertAlmostEqual(block.residual_after.bounds.max_z, -34, delta=0.2)
        self.assertAlmostEqual(block.cut_off.bounds.min_z, -30, delta=0.2)
        self.assertTrue(any("cut off" in message for message in plan.messages))

    def test_a_groove_that_stops_short_of_the_axis_leaves_one_piece(self):
        block = plan_program(self._program(bottom_radius_mm=1)).blocks[0]
        self.assertTrue(block.cut_off.is_empty)
