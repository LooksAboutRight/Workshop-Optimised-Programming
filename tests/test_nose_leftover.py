"""What the rounded nose of a tool cannot reach stays standing after the block: the next block and the picture get the real material
(the user, 2026-11-13). A sharp inner corner of the finished shape keeps the corner the nose leaves, about r squared times (1 - pi / 4)."""

import math
import unittest

from tests.helpers import simple_tool
from tests.test_rough_follow import holder_cnmg  # a tool with a nose radius of 0.8 mm
from wop.core.blocks.base import Safety
from wop.core.blocks.turning import TurningBlock, TurningSide
from wop.core.geometry.region import Region
from wop.core.program_model.operations import SpindleMode, SpindleSetting
from wop.core.program_model.program import Program, plan_program
from wop.core.program_model.raw_part import RawPart
from wop.core.tooling.tool_reference import nose_circle

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
RAW = RawPart("steel", 30, 60)  # radius 15, 60 long: 900 mm2 in the half section
CORNER = 1 - math.pi / 4


def program(tool, **overrides):
    values = dict(
        block_id="t", tool_number=1, spindle=SPINDLE, side=TurningSide.OUTSIDE, target_radius_mm=10, end_z_mm=-30,
        feed_mm_per_rev=0.25, depth_of_cut_mm=2, finish_allowance_mm=0.3, finish_pass=True, finish_feed_mm_per_rev=0.1,
    )
    values.update(overrides)
    return Program(raw_part=RAW, tools=(tool,), safety=Safety(25, 10, 1), blocks=(TurningBlock(**values),))


class NoseLeftoverTests(unittest.TestCase):
    def test_a_sharp_tool_leaves_exactly_the_finished_shape(self):
        block = plan_program(program(simple_tool(1))).blocks[0]
        self.assertAlmostEqual(block.residual_after.area, 900 - 150, delta=1e-3)

    def test_a_tool_with_a_nose_leaves_the_corner_it_cannot_reach(self):
        tool = holder_cnmg()
        radius = nose_circle(tool)[0]
        block = plan_program(program(tool)).blocks[0]
        extra = block.residual_after.area - (900 - 150)
        self.assertAlmostEqual(extra, radius ** 2 * CORNER, delta=0.02)  # the shoulder keeps its corner
        self.assertAlmostEqual(block.result.removed.area, 150 - extra, delta=1e-6)
        self.assertEqual(len(block.residual_after.pieces()), 1)  # it hangs on to the part: no piece is cut off
        self.assertFalse([note for note in block.result.messages if "cut off" in note])

    def test_the_picture_and_the_next_block_get_the_material_that_stands(self):
        plan = plan_program(program(holder_cnmg()))
        block = plan.blocks[0]
        self.assertEqual(block.residual_after, block.material_after)  # what the picture shows
        in_the_corner = block.residual_after.intersection(Region.rectangle(10, -30.01, 10.9, -29.0))
        self.assertGreater(in_the_corner.area, 0.1)  # the next block starts with it

    def test_a_large_leftover_is_told_and_a_small_one_stands_quietly(self):
        from tests.test_blocks_turning_contour import block as contour_block, context as contour_context, contour_of
        from wop.core.constants import UNREACHED_MIN_AREA_MM2

        tool = holder_cnmg()
        radius = nose_circle(tool)[0]
        self.assertLess(radius ** 2 * CORNER, UNREACHED_MIN_AREA_MM2)  # one inner corner is too small for a note
        steps = contour_of((8, 0), (8, -10), (12, -10), (12, -20), (14, -20), (14, -30))  # three inner corners
        result = contour_block(steps, finish_allowance_mm=0.3, finish_pass=True, finish_feed_mm_per_rev=0.1).generate(contour_context(steps, tool=tool))
        told = [note for note in result.messages if "stays standing" in note]
        self.assertEqual(len(told), 1, result.messages)
        self.assertIn("nose", told[0])
        single = plan_program(program(tool)).blocks[0].result.messages
        self.assertFalse([note for note in single if "stays standing" in note])


class RestMaterialCleanupTests(unittest.TestCase):
    """The project of the user (2026-11-13): a tool with a nose of 2 mm leaves the corner of a shoulder, a second tool with a nose of 0.1 mm
    cleans it up. The second tool must not go into the finished part (it did: the leftover had a flat top and a film along the part)."""

    def test_the_second_tool_cleans_the_corner_without_touching_the_part(self):
        from tests.helpers import project_path
        from wop.adapters.project_files import load_project
        from wop.core.verify import verify_plan

        project = load_project(project_path("nose_rest_cleanup.wop.json"))
        plan = plan_program(project.program)
        self.assertEqual(plan.left_out, ())
        first, second = plan.blocks
        self.assertTrue([note for note in first.result.messages if "stays standing" in note])  # the big nose leaves the corner and says so
        lowest = min(op.end.x for op in second.operations if hasattr(op, "feed_mm_per_rev"))
        self.assertGreaterEqual(lowest, 10 - 1e-6)  # the target radius: no move below it
        self.assertEqual([finding.message for finding in verify_plan(project.program, plan)], [])
        self.assertAlmostEqual(second.residual_after.area, 900 - 20 * 5, delta=0.05)  # the finished shape: the second block took the corner
        self.assertGreater(first.residual_after.area - second.residual_after.area, 0.5)  # what the first one left


if __name__ == "__main__":
    unittest.main()
