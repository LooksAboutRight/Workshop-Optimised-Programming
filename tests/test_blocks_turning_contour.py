import unittest

from tests.helpers import simple_tool
from wop.core.contour import ContourDefinition, LineStep
from wop.core.geometry import Point
from wop.core.program_model.operations import SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks.base import BlockContext, BlockError, Safety
from wop.core.blocks.turning import TurningBlock
from wop.core.blocks.turning_common import PassDirection, TurningSide
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.contour_solver import build_contour
from wop.core.program_model.stock import stock_region

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
AREA_TOLERANCE = 0.05


def contour_of(*points):
    steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
    return build_contour("c", "test", ContourDefinition(Point(*points[0]), steps))


def block(shape, **overrides):
    values = dict(
        block_id="c1", tool_number=1, spindle=SPINDLE, contour_id=shape.contour_id,
        side=TurningSide.OUTSIDE, feed_mm_per_rev=0.25, depth_of_cut_mm=2,
    )
    values.update(overrides)
    return ContourTurningBlock(**values)


def context(shape, raw_part=None, tool=None):
    raw_part = raw_part or RawPart("steel", 30, 60)
    safety = Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1)
    return BlockContext(
        raw_part, tool or simple_tool(1), stock_region(raw_part), safety, contours=(shape,)
    )


def generate(shape, raw_part=None, tool=None, **overrides):
    return block(shape, **overrides).generate(context(shape, raw_part, tool))


class ContourTurningTests(unittest.TestCase):
    def test_a_plain_cylinder_gives_the_same_moves_as_the_simple_form(self):
        shape = contour_of((10, 0), (10, -30))
        for direction in PassDirection:
            with self.subTest(direction=direction):
                simple = TurningBlock(
                    block_id="c1", tool_number=1, spindle=SPINDLE, side=TurningSide.OUTSIDE,
                    target_radius_mm=10, end_z_mm=-30, feed_mm_per_rev=0.25,
                    depth_of_cut_mm=2, finish_allowance_mm=0.3, pass_direction=direction,
                )
                a = simple.generate(context(shape))
                b = generate(shape, finish_allowance_mm=0.3, pass_direction=direction)  # along Z both plan it as a contour
                if direction is PassDirection.ALONG_Z:
                    self.assertEqual(a.operations[1:], b.operations[1:])
                else:  # across X the simple block retracts like facing, the contour block straight out
                    self.assertAlmostEqual(a.removed.area, b.removed.area, delta=AREA_TOLERANCE)

    def test_a_contour_that_starts_with_a_line_along_the_front_face_can_be_turned(self):
        # the first line lies on the front face: it used to lie on the closing edge of the outline ("crosses itself")
        shape = contour_of((2.5, 0), (10, 0), (10, -30))
        result = generate(shape)
        self.assertAlmostEqual(result.removed.area, (15 - 10) * 30, delta=AREA_TOLERANCE)

    def test_stock_in_front_of_the_contour_is_removed_too(self):
        shape = contour_of((10, -5), (10, -30))  # the material runs to Z 0, the contour starts at Z -5
        result = generate(shape)
        self.assertAlmostEqual(result.removed.area, (15 - 10) * 30, delta=AREA_TOLERANCE)  # 5 mm in front + 25 along

    def test_a_contour_larger_than_the_stock_does_not_crash(self):
        shape = contour_of((8, 0), (8, -10), (20, -10), (20, -30))  # the last steps are bigger than the stock
        result = generate(shape)
        self.assertAlmostEqual(result.removed.area, (15 - 8) * 10, delta=AREA_TOLERANCE)

    def test_a_stepped_shaft_removes_both_steps(self):
        result = generate(contour_of((8, 0), (8, -15), (12, -15), (12, -30)))
        self.assertAlmostEqual(result.removed.area, 7 * 15 + 3 * 15, delta=AREA_TOLERANCE)
        self.assertEqual(result.messages, ())

    def test_both_pass_directions_remove_the_same_on_a_stepped_shaft(self):
        shape = contour_of((8, 0), (8, -15), (12, -15), (12, -30))
        a = generate(shape)
        b = generate(shape, pass_direction=PassDirection.ALONG_X)
        self.assertAlmostEqual(a.removed.area, b.removed.area, delta=AREA_TOLERANCE)

    def test_a_groove_the_tool_is_too_wide_for_is_finished_as_drawn(self):
        from wop.core.program_model.operations import LinearMove
        shape = contour_of((10, 0), (10, -10), (6, -10), (6, -14), (10, -14), (10, -30))
        result = generate(shape)
        self.assertFalse(any("not finished" in m for m in result.messages))  # nothing is left out
        bottom = [op for op in result.operations if isinstance(op, LinearMove) and abs(op.end.x - 6) < 1e-6]
        self.assertTrue(bottom)  # the finishing goes down to the bottom of the groove, as drawn (the checker reports the collision)

    def test_the_roughing_is_planned_from_the_stock_and_never_goes_deeper_than_the_depth_of_cut(self):
        from wop.core.program_model.operations import LinearMove
        shape = contour_of((8, 0), (8, -10), (12, -10), (12, -30))
        for direction in PassDirection:
            with self.subTest(direction=direction):
                result = generate(shape, pass_direction=direction, depth_of_cut_mm=1.5)
                rough = [op for op in result.operations if isinstance(op, LinearMove) and op.feed_mm_per_rev == 0.25]
                self.assertTrue(rough)  # the roughing is there, whatever the tool could reach
                levels = sorted({round(op.end.x if direction is PassDirection.ALONG_Z else op.end.z, 6) for op in rough})
                self.assertTrue(all(b - a <= 1.5 + 1e-6 for a, b in zip(levels, levels[1:])))

    def test_a_bore_follows_the_contour(self):
        tube = RawPart("steel", 40, 50, inner_diameter_mm=14)
        result = generate(
            contour_of((10, 0), (10, -25)), tube, simple_tool(1, side=-1), side=TurningSide.INSIDE
        )
        self.assertAlmostEqual(result.removed.area, 3 * 25, delta=AREA_TOLERANCE)
        self.assertEqual(result.messages, ())

    def test_a_contour_that_does_not_end_at_its_lowest_z_is_refused(self):
        with self.assertRaises(BlockError):
            generate(contour_of((10, 0), (10, -20), (12, -10)))

    def test_a_missing_contour_is_refused(self):
        shape = contour_of((10, 0), (10, -30))
        with self.assertRaises(BlockError):
            block(shape, contour_id="nothing").generate(context(shape))

    def test_the_block_names_its_contour(self):
        shape = contour_of((10, 0), (10, -30))
        self.assertEqual(block(shape).contour_ids, ("c",))

    def test_the_block_is_registered(self):
        from wop.core.blocks import BLOCK_TYPES

        self.assertIn("turning_contour", BLOCK_TYPES.names())


if __name__ == "__main__":
    unittest.main()
