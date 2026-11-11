"""Where the analytic planner used to hand a block to the old planner (step 3 of the branch, 2026-10-25): it plans it by the rules instead.
A cut with no free way to it gets the long way (out beyond the stock and in) and a note, the checker says whether it is free; a line the
planner cannot work out is not cut and a note says so; material the planner cannot read leaves the block out with the reason. No project
meets these cases, so the tests make them by patching the planner (they plan by themselves, never through `tests.helpers.planned`)."""

import unittest
from dataclasses import replace
from unittest import mock

from tests.test_rough_follow import generate, holder_cnmg
from wop.core.analytic import rapids as rapids_module
from wop.core.geometry.chains import ChainError
from wop.core.blocks.base import BlockError
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.program_model.operations import Rapid
from wop.core.program_model.raw_part import RawPart

RAW = RawPart("steel", 40, 60)
SHAPE = [(8, 0), (8, -10), (14, -16), (14, -30)]


def plan(**overrides):
    result, _shape = generate(SHAPE, holder_cnmg(), RAW, finish_pass=False, **overrides)
    return result


class NoFreeWayTests(unittest.TestCase):
    def test_the_long_way_and_a_note_and_no_old_planner(self):
        with mock.patch.object(rapids_module, "_way", lambda *arguments: None):
            result = plan()
        text = " ".join(result.messages)
        self.assertIn("no free way was found between two cuts: the tool goes out beyond the stock and back in", text)
        self.assertNotIn("old planner", text)
        rapids = [op for op in result.operations if isinstance(op, Rapid)]
        stock_radius = RAW.outer_diameter_mm / 2
        self.assertTrue(any(op.end.x > stock_radius for op in rapids))  # out beyond the stock

    def test_every_cut_gets_its_way_from_where_the_cut_before_ended(self):
        from tests.test_rough_follow import block
        from wop.core.blocks.base import BlockContext, Safety
        from wop.core.contour import Contour, ContourDefinition, LineStep
        from wop.core.contour_solver import solve_contour
        from wop.core.geometry import Point
        from wop.core.program_model.stock import stock_region

        definition = ContourDefinition(Point(*SHAPE[0]), tuple(LineStep(Point(x, z)) for x, z in SHAPE[1:]))
        shape = Contour("c", "test", tuple(solve_contour(definition)), definition)
        context = BlockContext(RAW, holder_cnmg(), stock_region(RAW), Safety(30, 10, 1), contours=(shape,))
        with mock.patch.object(rapids_module, "_way", lambda *arguments: None):
            found = block(finish_pass=False).roughing_cuts(context)
        self.assertGreater(found.unconnected_cuts, 0)
        for before, listed in zip(found.cuts, found.cuts[1:]):
            if listed.joined:
                continue
            with self.subTest(start=listed.start):
                self.assertTrue(listed.rapid)  # no jump: a feed move straight to the next cut would go through the material
                ended = (before.ride[-1].end if before.ride else before.end)
                self.assertTrue(listed.rapid[0].start.is_close(ended, 1e-6))
                arrives = listed.entry[0].start if listed.entry else listed.start
                self.assertTrue(listed.rapid[-1].end.is_close(arrives, 1e-6))
        self.assertTrue(found.leave_rapid)

    def test_the_same_material_is_removed(self):
        normal = plan()
        with mock.patch.object(rapids_module, "_way", lambda *arguments: None):
            long_way = plan()
        self.assertAlmostEqual(normal.removed.area, long_way.removed.area, delta=0.01)


class LinesNotWorkedOutTests(unittest.TestCase):
    def test_a_note_says_they_stay_and_the_old_planner_does_not_take_over(self):
        real = ContourTurningBlock.roughing_cuts

        def with_failed(self, context, run_on=0.0):
            found = real(self, context, run_on)
            return replace(found, failed_lines=2) if found is not None else None

        with mock.patch.object(ContourTurningBlock, "roughing_cuts", with_failed):
            result = plan()
        text = " ".join(result.messages)
        self.assertIn("2 roughing line(s) could not be worked out and are not cut", text)
        self.assertNotIn("old planner", text)


class UnreadableMaterialTests(unittest.TestCase):
    def test_the_block_is_refused_with_the_reason(self):
        def broken(self, context, run_on=0.0):
            raise ChainError("a needle in the border")

        with mock.patch.object(ContourTurningBlock, "roughing_cuts", broken), self.assertRaises(BlockError) as caught:
            plan()
        self.assertIn("cannot read the material of this block", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
