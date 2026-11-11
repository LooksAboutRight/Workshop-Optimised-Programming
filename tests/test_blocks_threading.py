import unittest

from wop.core.program_model.operations import Rapid, SpindleMode, SpindleSetting, ThreadOperation, ThreadTaper

from wop.core.geometry import Point
from wop.core.blocks.base import BlockError, Safety
from wop.core.blocks.threading import ThreadingBlock
from wop.core.blocks.turning_common import TurningSide
from wop.core.program_model.program import Program, plan_program
from wop.core.program_model.raw_part import RawPart
from wop.core.tooling.tool_presets import thread_tool
from wop.core.program_model.units import XInputMode
from wop.core.verify import verify_plan
from wop.post.base import PostSettings
from wop.post.generate import generate_gcode
from tests.post_helpers import shipped_post

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 400)
SAFETY_ARGS = dict(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1)


def operation(**overrides):
    values = dict(
        start_x=16, start_z=4.5, end_z=-15, pitch_mm=1.5, peak_offset_mm=-1, first_cut_mm=0.3,
        depth_mm=0.92, degression=2, compound_angle_deg=29.5, spring_passes=1,
    )
    values.update(overrides)
    return ThreadOperation(**values)


class ThreadOperationTests(unittest.TestCase):
    def test_passes_get_shallower_steps_and_end_at_full_depth_with_spring_passes(self):
        depths = operation().pass_depths()
        self.assertAlmostEqual(depths[0], 0.3)
        self.assertAlmostEqual(depths[1], 0.3 * 2 ** 0.5)
        self.assertEqual(depths[-2:], [0.92, 0.92])
        self.assertEqual(sorted(depths), depths)

    def test_the_explicit_moves_stay_at_the_crest_radius_or_below_it(self):
        moves = operation().explicit_moves()
        feeds = [m for m in moves if hasattr(m, "feed_mm_per_rev")]
        self.assertEqual(len(feeds), len(operation().pass_depths()))
        self.assertTrue(all(m.end.x <= 15 for m in feeds))
        self.assertTrue(all(m.feed_mm_per_rev == 1.5 for m in feeds))

    def test_an_inside_thread_cuts_outwards(self):
        moves = operation(start_x=8, peak_offset_mm=1).explicit_moves()
        feeds = [m for m in moves if hasattr(m, "feed_mm_per_rev")]
        self.assertTrue(all(m.end.x >= 9 for m in feeds))


def program(block, tool=None, raw=None):
    return Program(
        raw_part=raw or RawPart("steel", 30, 60), tools=(tool or thread_tool(1, "thread"),),
        safety=Safety(**SAFETY_ARGS), blocks=(block,),
    )


def block(**overrides):
    values = dict(
        block_id="t1", tool_number=1, spindle=SPINDLE, side=TurningSide.OUTSIDE,
        crest_radius_mm=15, pitch_mm=1.5, start_z_mm=0, end_z_mm=-15,
    )
    values.update(overrides)
    return ThreadingBlock(**values)


class ThreadingTests(unittest.TestCase):
    def test_bad_values_are_refused(self):
        for overrides in (
            dict(pitch_mm=0), dict(crest_radius_mm=0), dict(end_z_mm=0), dict(end_z_mm=5), dict(spring_passes=-1),
            dict(degression=0.5), dict(compound_angle_deg=-1), dict(compound_angle_deg=90), dict(taper_distance_mm=-1),
        ):
            with self.subTest(overrides=overrides), self.assertRaises(BlockError):
                block(**overrides)

    def test_the_iso_depth_comes_from_the_pitch(self):
        self.assertAlmostEqual(block().depth(), 0.6134 * 1.5)
        self.assertAlmostEqual(block(side=TurningSide.INSIDE).depth(), 0.5413 * 1.5)
        self.assertEqual(block(thread_depth_mm=1).depth(), 1)

    def test_the_example_plans_without_findings_and_writes_a_cycle(self):
        example = ThreadingBlock.example("t1", 1, SPINDLE)
        prog = program(example)
        plan = plan_program(prog)
        self.assertEqual(plan.blocks[0].result.messages, ())
        self.assertEqual(verify_plan(prog, plan), [])
        text = generate_gcode(plan, shipped_post(), PostSettings(XInputMode.RADIUS)).text
        self.assertEqual(text.count("G76 "), 1)
        self.assertIn("G76 P1.5 Z-15 I-1 J0.3 K0.92 R2 Q29.5 H1", text)

    def test_the_removed_area_is_the_band_of_the_thread_depth_plus_the_flank_run_out(self):
        plan = plan_program(program(block(thread_depth_mm=1)))
        run_out = 1 * 0.5773502691896257
        self.assertAlmostEqual(plan.blocks[0].result.removed.area, 1 * (15 + 2 * run_out), delta=0.6)  # the sandbox stand-in is coarse, the exact region is exact

    def test_material_beyond_the_crest_is_refused(self):
        plan = plan_program(program(block(crest_radius_mm=12)))
        result = plan.blocks[0].result
        self.assertTrue(result.messages)
        self.assertIn("turn or bore", result.messages[0])
        self.assertFalse([op for op in result.operations if isinstance(op, ThreadOperation)])

    def test_an_inside_thread_in_a_bore(self):
        raw = RawPart("steel", 100, 60, inner_diameter_mm=80)  # wide enough for the 28 mm long tool body
        tool = thread_tool(1, "inside", body_towards_larger_x=False)
        prog = program(block(side=TurningSide.INSIDE, crest_radius_mm=40, end_z_mm=-12), tool, raw)
        plan = plan_program(prog)
        self.assertEqual(plan.blocks[0].result.messages, ())
        self.assertEqual(verify_plan(prog, plan), [])
        self.assertEqual([op for op in plan.blocks[0].operations if isinstance(op, ThreadOperation)][0].peak_offset_mm, 1)


class ThreadingSpindleTests(unittest.TestCase):
    def test_a_surface_speed_becomes_the_rpm_at_the_crest(self):
        css = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 100, 3000)
        spindle = block(spindle=css).spindle
        self.assertIs(spindle.mode, SpindleMode.CONSTANT_RPM)
        self.assertIsNone(spindle.rpm_limit)
        self.assertAlmostEqual(spindle.value, 100 * 1000 / (3.141592653589793 * 30))

    def test_a_fixed_rpm_stays(self):
        self.assertEqual(block().spindle, SPINDLE)

    def test_an_rpm_above_the_machine_maximum_is_a_finding(self):
        from wop.core.lathe.machine import MachineDef
        from wop.core.lathe.machine_check import check_against_machine
        prog = program(block(spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, 5000)))
        machine = MachineDef(name="m", max_rpm=3000)
        messages = check_against_machine(prog, plan_program(prog), machine)
        self.assertTrue(any("5000 RPM is above the maximum of 3000 RPM" in m for m in messages), messages)


class ThreadingFormTests(unittest.TestCase):
    def specs(self, **overrides):
        from wop.ui.block_forms import form_for
        return form_for(block(**overrides))

    def test_no_spindle_mode_and_no_limit_and_the_value_is_the_rpm(self):
        specs = self.specs()
        paths = [spec.path for spec in specs]
        self.assertNotIn(("spindle", "mode"), paths)
        self.assertNotIn(("spindle", "rpm_limit"), paths)
        self.assertEqual(next(s for s in specs if s.path == ("spindle", "value")).label, "Spindle RPM")

    def test_the_order_of_the_form(self):
        names = list(dict.fromkeys(spec.path[0] for spec in self.specs()))
        self.assertEqual(names, [
            "name", "side", "designation", "tool_number", "spindle", "crest_radius_mm", "pitch_mm", "start_z_mm", "end_z_mm",
            "thread_depth_mm", "first_cut_depth_mm", "degression", "compound_angle_deg", "spring_passes",
            "taper", "taper_distance_mm", "coolant",
        ])

    def test_the_end_can_be_shown_as_a_length_and_the_taper_length_waits_for_a_taper(self):
        specs = self.specs()
        end = next(s for s in specs if s.path == ("end_z_mm",))
        self.assertEqual((end.label, end.relative_to, end.relative_label), ("End Z", "start_z_mm", "Length"))
        self.assertFalse(next(s for s in specs if s.path == ("taper_distance_mm",)).enabled)
        tapered = self.specs(taper=ThreadTaper.EXIT, taper_distance_mm=2)
        self.assertTrue(next(s for s in tapered if s.path == ("taper_distance_mm",)).enabled)

    def test_length_and_end_convert_into_each_other(self):
        from wop.ui.block_forms import end_to_length, length_to_end
        self.assertEqual(end_to_length(-10, -30), 20)
        self.assertEqual(length_to_end(-10, 20), -30)


class ThreadingPathTests(unittest.TestCase):
    def test_the_g76_values_reach_the_operation(self):
        prog = program(block(degression=1.5, compound_angle_deg=30, spring_passes=2, first_cut_depth_mm=0.2,
                             taper=ThreadTaper.BOTH, taper_distance_mm=2))
        op = [o for o in plan_program(prog).blocks[0].operations if isinstance(o, ThreadOperation)][0]
        self.assertEqual((op.degression, op.compound_angle_deg, op.spring_passes, op.first_cut_mm), (1.5, 30, 2, 0.2))
        self.assertEqual((op.taper, op.taper_distance_mm), (ThreadTaper.BOTH, 2))

    def test_a_taper_without_a_length_is_a_finding_and_the_thread_is_cut_without_it(self):
        for overrides in (dict(taper=ThreadTaper.ENTRY), dict(taper=ThreadTaper.BOTH, taper_distance_mm=8)):
            with self.subTest(overrides=overrides):
                block(**overrides)  # the entry is accepted: the taper can be chosen before its length is typed
                result = plan_program(program(block(**overrides))).blocks[0].result
                self.assertTrue(any("without a taper" in m for m in result.messages), result.messages)
                op = [o for o in result.operations if isinstance(o, ThreadOperation)][0]
                self.assertEqual((op.taper, op.taper_distance_mm), (ThreadTaper.NONE, 0))

    def test_a_taper_with_a_fitting_length_gives_no_finding(self):
        result = plan_program(program(block(taper=ThreadTaper.EXIT, taper_distance_mm=3))).blocks[0].result
        self.assertEqual(result.messages, ())

    def test_a_thread_in_front_of_the_face_says_that_z_is_absolute(self):
        plan = plan_program(program(block(start_z_mm=25, end_z_mm=10)))
        self.assertTrue(any("not in the material" in m and "absolute" in m for m in plan.blocks[0].result.messages))

    def test_an_inside_thread_starts_with_x_at_the_safe_z_and_ends_at_the_safe_point(self):
        raw = RawPart("steel", 100, 60, inner_diameter_mm=80)  # wide enough for the 28 mm long tool body
        tool = thread_tool(1, "inside", body_towards_larger_x=False)
        plan = plan_program(program(block(side=TurningSide.INSIDE, crest_radius_mm=40, end_z_mm=-12), tool, raw))
        moves = [op for op in plan.blocks[0].operations if isinstance(op, (Rapid, ThreadOperation))]
        self.assertEqual((moves[1].end.x, moves[1].end.z), (39, 10))  # first X to the start X at the safe Z (move 0 is the tool change)
        self.assertEqual(moves[-1].end, Point(25, 10))

    def test_an_outside_thread_ends_at_the_safe_point(self):
        plan = plan_program(program(block()))
        last = [op for op in plan.blocks[0].operations if isinstance(op, Rapid)][-1]
        self.assertEqual(last.end, Point(25, 10))


class ThreadingProjectTests(unittest.TestCase):
    def test_an_old_project_with_a_length_gets_an_absolute_end(self):
        from wop.core.files.project_io import _block_from_data
        data = {"type": "threading", "parameters": {
            "block_id": "t1", "tool_number": 1, "spindle": {"mode": "CONSTANT_SURFACE_SPEED", "value": 120.0, "rpm_limit": None},
            "coolant": "NONE", "name": "Thread", "comment": "", "side": "OUTSIDE", "crest_radius_mm": 15.0,
            "pitch_mm": 1.5, "start_z_mm": -5.0, "length_mm": 20.0, "thread_depth_mm": None,
            "first_cut_depth_mm": 0.3, "spring_passes": 1,
        }}
        loaded = _block_from_data(data)
        self.assertEqual(loaded.end_z_mm, -25)
        self.assertEqual(loaded.length_mm, 20)
        self.assertIs(loaded.spindle.mode, SpindleMode.CONSTANT_RPM)


if __name__ == "__main__":
    unittest.main()
