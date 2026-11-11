import math
import unittest

from wop.core.geometry import Point
from wop.core.constants import DRILL_TIP_ANGLE_DEG
from wop.core.program_model.operations import DrillMode, DrillOperation, LinearMove, Rapid, SpindleMode, SpindleSetting, plain_moves
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks.base import BlockContext, BlockError, Safety
from wop.core.blocks.drilling import DrillingBlock
from wop.core.program_model.program import Program, plan_program
from wop.core.geometry.region import Region
from wop.core.program_model.stock import stock_region
from wop.core.tooling.tool_presets import drill_tool
from wop.core.verify import verify_plan
from wop.post.base import PostSettings
from wop.post.generate import generate_gcode
from tests.post_helpers import expanded_post
from wop.core.program_model.units import XInputMode

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1500)
SAFETY_ARGS = dict(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1)


class DrillOperationTests(unittest.TestCase):
    def test_one_stroke_feeds_down_and_retracts(self):
        moves = DrillOperation(1, -14, 0.1).explicit_moves()
        self.assertEqual(moves, (LinearMove(Point(0, -14), 0.1), Rapid(Point(0, 1))))

    def test_a_peck_depth_without_a_mode_retracts_fully(self):
        moves = DrillOperation(1, -14, 0.1, peck_depth_mm=5).explicit_moves()
        feeds = [m.end.z for m in moves if isinstance(m, LinearMove)]
        self.assertEqual(len(feeds), 3)
        self.assertAlmostEqual(feeds[-1], -14)
        self.assertEqual(moves[-1], Rapid(Point(0, 1)))

    def test_the_three_modes_with_dwell_and_exit(self):
        def path(mode, **extra):
            operation = DrillOperation(1, -14, 0.1, 5, mode, entry_z=0, exit_z=10, **extra)
            return [
                ("F" if isinstance(m, LinearMove) else "R" if isinstance(m, Rapid) else "D", m.end.z if hasattr(m, "end") else m.seconds)
                for m in operation.explicit_moves()
            ]
        self.assertEqual(path(DrillMode.DRILL), [("F", -14), ("R", 10)])
        self.assertEqual(path(DrillMode.DRILL, dwell_s=2), [("F", -14), ("D", 2), ("R", 10)])
        self.assertEqual(path(DrillMode.PECK_FULL_RETRACT, dwell_s=2), [
            ("F", -5), ("R", 1), ("R", -4.75), ("F", -10), ("R", 1), ("R", -9.75), ("F", -14), ("D", 2), ("R", 10),
        ])
        # Peck drilling: after a peck the drill goes back only to where that peck began.
        self.assertEqual(path(DrillMode.PECK), [
            ("F", -5), ("R", 1), ("R", -4.75), ("F", -10), ("R", -4.75), ("R", -9.75), ("F", -14), ("R", 10),
        ])

    def test_a_known_hole_is_rapided_through_and_the_pecks_start_below_it(self):
        def path(mode):
            operation = DrillOperation(1, -21.8026, 0.1, 5, mode, entry_z=0, exit_z=10, air_z=-12.0043)
            return [("F" if isinstance(m, LinearMove) else "R", m.end.z) for m in operation.explicit_moves()]
        self.assertEqual(path(DrillMode.PECK_FULL_RETRACT), [
            ("R", -12.0043), ("F", -17.0043), ("R", 1), ("R", -16.7543), ("F", -21.8026), ("R", 10),
        ])
        self.assertEqual(path(DrillMode.PECK), [
            ("R", -12.0043), ("F", -17.0043), ("R", -12.0043), ("R", -16.7543), ("F", -21.8026), ("R", 10),
        ])

    def test_the_last_peck_is_as_short_as_the_depth_needs(self):
        stops = DrillOperation(1, -12, 0.1, 5, DrillMode.PECK, entry_z=0).stops()
        self.assertEqual(stops, [-5, -10, -12])

    def test_the_dwell_is_not_a_move_for_the_pictures(self):
        operation = DrillOperation(1, -14, 0.1, dwell_s=2)
        self.assertEqual(plain_moves(operation), (LinearMove(Point(0, -14), 0.1), Rapid(Point(0, 1))))

    def test_no_depth_gives_no_moves(self):
        self.assertEqual(DrillOperation(1, 1, 0.1).explicit_moves(), ())


def block(**overrides):
    values = dict(
        block_id="d1", tool_number=1, spindle=SPINDLE, depth_z_mm=-15,
        feed_mm_per_rev=0.1,
    )
    values.update(overrides)
    return DrillingBlock(**values)


def program(drilling, tool=None):
    return Program(
        raw_part=RawPart("steel", 30, 60), tools=(tool or drill_tool(1, "drill"),),
        safety=Safety(**SAFETY_ARGS), blocks=(drilling,),
    )


class DrillingTests(unittest.TestCase):
    def test_bad_values_are_refused(self):
        for overrides in (
            dict(feed_mm_per_rev=0), dict(peck_depth_mm=0), dict(dwell_s=-1),
        ):
            with self.subTest(overrides=overrides), self.assertRaises(BlockError):
                block(**overrides)

    def test_a_peck_depth_far_too_small_is_refused_not_planned_for_ever(self):
        raw = RawPart("steel", 30, 60)
        context = BlockContext(raw, drill_tool(1, "d"), stock_region(raw), Safety(**SAFETY_ARGS))
        with self.assertRaises(BlockError):
            block(drill_mode=DrillMode.PECK, peck_depth_mm=0.0001).generate(context)  # a typed 0.0001 for 0.1: 150000 pecks

    def test_a_peck_mode_without_a_peck_depth_takes_the_preset(self):
        from wop.core.constants import EXAMPLE_DRILL_PECK_MM

        self.assertEqual(block(drill_mode=DrillMode.PECK).peck_depth_mm, EXAMPLE_DRILL_PECK_MM)
        self.assertIsNone(block().peck_depth_mm)  # drilling: no peck depth

    def test_a_new_block_opens_with_the_preferences_of_the_drill_section(self):
        from unittest import mock

        from wop.core.blocks import drilling
        from wop.core.program_model.operations import SpindleMode, SpindleSetting

        spindle = SpindleSetting(SpindleMode.CONSTANT_RPM, 500)
        with mock.patch.multiple(
            drilling, EXAMPLE_DRILL_MODE="drilling", EXAMPLE_DRILL_DEPTH_MM=20, EXAMPLE_DRILL_TO_FULL_DIAMETER="no",
            EXAMPLE_DRILL_FEED_MM_PER_REV=0.2, EXAMPLE_DRILL_DWELL_S=1.5,
        ):
            new = drilling.DrillingBlock.example("b1", 1, spindle)
        self.assertEqual((new.drill_mode, new.depth_z_mm, new.depth_to_full_diameter), (DrillMode.DRILL, -20, False))
        self.assertEqual((new.feed_mm_per_rev, new.peck_depth_mm, new.dwell_s), (0.2, None, 1.5))
        standard = drilling.DrillingBlock.example("b2", 1, spindle)
        self.assertEqual((standard.drill_mode, standard.depth_z_mm, standard.peck_depth_mm), (DrillMode.PECK, -15, 5))

    def test_the_hole_is_as_wide_as_the_drill_and_as_deep_as_asked(self):
        raw = RawPart("steel", 30, 60)
        context = BlockContext(raw, drill_tool(1, "d"), stock_region(raw), Safety(**SAFETY_ARGS))
        result = block().generate(context)
        self.assertEqual(result.messages, ())
        point = 3 / math.tan(math.radians(DRILL_TIP_ANGLE_DEG) / 2)
        self.assertAlmostEqual(result.removed.area, 3 * 15 + 3 * point / 2, delta=0.05)
        drill = [op for op in result.operations if isinstance(op, DrillOperation)]
        self.assertEqual(len(drill), 1)
        self.assertAlmostEqual(drill[0].end_z, -15 - point)

    def test_a_second_drill_only_takes_what_is_left(self):
        raw = RawPart("steel", 30, 60)
        pilot = Region.rectangle(0, -15, 1.5, 0)
        context = BlockContext(
            raw, drill_tool(1, "d", diameter_mm=6), stock_region(raw).difference(pilot), Safety(**SAFETY_ARGS)
        )
        result = block().generate(context)
        point = 3 / math.tan(math.radians(DRILL_TIP_ANGLE_DEG) / 2)
        self.assertAlmostEqual(result.removed.area, 3 * 15 + 3 * point / 2 - 1.5 * 15, delta=0.05)

    def test_the_depth_can_be_measured_to_the_drill_tip(self):
        raw = RawPart("steel", 30, 60)
        context = BlockContext(raw, drill_tool(1, "d"), stock_region(raw), Safety(**SAFETY_ARGS))
        point = 3 / math.tan(math.radians(DRILL_TIP_ANGLE_DEG) / 2)
        tip = block(depth_to_full_diameter=False).generate(context)
        self.assertEqual(tip.messages, ())
        self.assertAlmostEqual([op for op in tip.operations if isinstance(op, DrillOperation)][0].end_z, -15)
        self.assertAlmostEqual(tip.removed.area, 3 * (15 - point) + 3 * point / 2, delta=0.05)
        full = block().generate(context)
        self.assertAlmostEqual([op for op in full.operations if isinstance(op, DrillOperation)][0].end_z, -15 - point)

    def test_a_drill_that_starts_at_the_safe_point_goes_to_the_axis_first_then_down(self):
        raw = RawPart("steel", 30, 60)
        context = BlockContext(raw, drill_tool(1, "d"), stock_region(raw), Safety(**SAFETY_ARGS))
        operations = block().generate(context).operations
        self.assertEqual(operations[1:3], (Rapid(Point(0, 10)), Rapid(Point(0, 1))))
        self.assertIsNone([op for op in operations if isinstance(op, DrillOperation)][0].air_z)

    def test_a_second_drill_rapids_through_the_hole_of_the_first(self):
        prog = Program(
            raw_part=RawPart("steel", 30, 60),
            tools=(drill_tool(4, "d10", diameter_mm=10), drill_tool(3, "d6", diameter_mm=6)),
            safety=Safety(**SAFETY_ARGS),
            blocks=(
                block(block_id="b1", tool_number=4, depth_z_mm=-10, drill_mode=DrillMode.PECK_FULL_RETRACT, peck_depth_mm=5),
                block(block_id="b2", tool_number=3, depth_z_mm=-20, drill_mode=DrillMode.PECK_FULL_RETRACT, peck_depth_mm=5),
            ),
        )
        plan = plan_program(prog)
        first = [op for op in plan.blocks[0].result.operations if isinstance(op, DrillOperation)][0]
        second = [op for op in plan.blocks[1].result.operations if isinstance(op, DrillOperation)][0]
        self.assertIsNone(first.air_z)
        self.assertAlmostEqual(first.end_z, -10 - 5 / math.tan(math.radians(DRILL_TIP_ANGLE_DEG) / 2))
        # the 6 mm drill touches the cone bottom of the 10 mm hole with its point: that depth plus the clearance
        self.assertAlmostEqual(second.air_z, first.end_z + 1, delta=0.2)
        moves = second.explicit_moves()
        self.assertEqual(moves[0], Rapid(Point(0, second.air_z)))
        self.assertAlmostEqual(moves[1].end.z, second.air_z - 5)  # the first peck is measured from there
        self.assertEqual(moves[2], Rapid(Point(0, 1)))  # full retract: back to the clearance in front of the face

    def test_the_first_drill_of_the_users_project_as_he_wrote_it(self):
        from wop.core.program_model.operation_text import describe_operations
        prog = Program(
            raw_part=RawPart("steel", 30, 60), tools=(drill_tool(4, "d10", diameter_mm=10),),
            safety=Safety(**SAFETY_ARGS),
            blocks=(block(block_id="b1", name="Drill", tool_number=4, spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, 1000),
                          depth_z_mm=-10, drill_mode=DrillMode.PECK_FULL_RETRACT, peck_depth_mm=5),),
        )
        lines = describe_operations(plan_program(prog).blocks[0].operations, single_moves=True).splitlines()[2:]
        self.assertEqual(lines, [
            "BEGIN    block b1 (drilling) Drill",
            "RAPID    X25 Z10", "TOOL     T4", "SPINDLE  1000 rpm", "RAPID    X0 Z10", "RAPID    X0 Z1",
            "DRILL    peck drilling, full retract: from Z1 to Z-13.0043, feed 0.1, pecks of 5, out to Z10",
            "    FEED     X0 Z-5  feed 0.1", "    RAPID    X0 Z1", "    RAPID    X0 Z-4.75",
            "    FEED     X0 Z-10  feed 0.1", "    RAPID    X0 Z1", "    RAPID    X0 Z-9.75",
            "    FEED     X0 Z-13.0043  feed 0.1", "    RAPID    X0 Z10",
            "RAPID    X25 Z10", "END      block b1",
        ])

    def test_the_example_plans_without_findings(self):
        example = DrillingBlock.example("d1", 1, SPINDLE)
        prog = program(example)
        plan = plan_program(prog)
        self.assertEqual(plan.blocks[0].result.messages, ())
        self.assertEqual(verify_plan(prog, plan), [])

    def test_gcode_has_explicit_feed_moves_on_the_axis(self):
        prog = program(block(drill_mode=DrillMode.PECK_FULL_RETRACT, peck_depth_mm=5))
        text = generate_gcode(plan_program(prog), expanded_post(), PostSettings(XInputMode.RADIUS)).text
        self.assertEqual(text.count("G1 Z"), 4)  # 16 mm from the retract plane, pecks of at most 5; X0 is written once, on the rapid before them

    def test_the_drill_leaves_to_the_safe_z_after_the_dwell(self):
        raw = RawPart("steel", 30, 60)
        context = BlockContext(raw, drill_tool(1, "d"), stock_region(raw), Safety(**SAFETY_ARGS))
        result = block(dwell_s=1.5).generate(context)
        operation = [op for op in result.operations if isinstance(op, DrillOperation)][0]
        self.assertEqual(operation.dwell_s, 1.5)
        self.assertEqual(operation.entry_z, 0)
        self.assertEqual(operation.retract_z, 1)  # the clearance in front of the face
        self.assertEqual(operation.exit_z, SAFETY_ARGS["safe_z_mm"])
        self.assertEqual(result.operations[-2], Rapid(Point(SAFETY_ARGS["safe_radius_mm"], SAFETY_ARGS["safe_z_mm"])))

    def test_the_dwell_reaches_the_gcode(self):
        text = generate_gcode(plan_program(program(block(dwell_s=1.5))), expanded_post(), PostSettings(XInputMode.RADIUS)).text
        self.assertIn("G4 P1.5", text.splitlines())

    def test_an_old_project_block_is_converted(self):
        from wop.core.blocks import BLOCK_TYPES  # noqa: F401
        from wop.core.files.project_io import _block_from_data
        parameters = {"block_id": "d", "tool_number": 1, "spindle": {"mode": "CONSTANT_RPM", "value": 1000, "rpm_limit": None},
                      "start_z_mm": -2, "depth_mm": 10, "feed_mm_per_rev": 0.1, "peck_depth_mm": 4}
        converted = _block_from_data({"type": "drilling", "parameters": parameters})
        self.assertEqual((converted.depth_z_mm, converted.drill_mode), (-12, DrillMode.PECK_FULL_RETRACT))
        parameters.pop("peck_depth_mm")
        self.assertEqual(_block_from_data({"type": "drilling", "parameters": parameters}).drill_mode, DrillMode.DRILL)

    def test_the_form_has_the_wanted_order_and_the_peck_depth_follows_the_mode(self):
        block_ = block()
        fields = block_.form_fields()
        self.assertEqual(fields[:4], ("name", "drill_mode", "tool_number", "spindle"))
        self.assertEqual(fields[-1], "coolant")
        self.assertLess(fields.index("feed_mm_per_rev"), fields.index("depth_z_mm"))
        self.assertEqual(fields[fields.index("depth_z_mm") + 1], "depth_to_full_diameter")
        self.assertLess(fields.index("depth_z_mm"), fields.index("peck_depth_mm"))
        self.assertLess(fields.index("peck_depth_mm"), fields.index("dwell_s"))
        self.assertIn("peck_depth_mm", block_.form_disabled())
        self.assertNotIn("peck_depth_mm", block(drill_mode=DrillMode.PECK, peck_depth_mm=5).form_disabled())

    def test_a_hole_outside_the_material_removes_nothing(self):
        result = block(depth_z_mm=5).generate(
            BlockContext(RawPart("steel", 30, 60), drill_tool(1, "d"), stock_region(RawPart("steel", 30, 60)), Safety(**SAFETY_ARGS))
        )
        self.assertTrue(result.removed.is_empty)


if __name__ == "__main__":
    unittest.main()
