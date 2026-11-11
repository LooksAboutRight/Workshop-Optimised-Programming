import unittest
from dataclasses import replace

from wop.core.constants import POWER_EFFICIENCY, POWER_FORMULA_DIVISOR
from wop.core.lathe.machine import AxisLimits, MachineDef
from wop.core.material import Material
from wop.core.program_model.operations import SpindleMode, SpindleSetting
from wop.core.lathe.spindle import cutting_speed_at, rpm_at

from wop.core.blocks.base import Safety
from wop.core.blocks.turning import TurningBlock
from wop.core.blocks.turning_common import TurningSide
from wop.core.lathe.machine_check import check_against_machine
from wop.core.lathe.power import estimate_power
from wop.core.program_model.program import Program, plan_program
from wop.core.program_model.raw_part import RawPart
from tests.helpers import simple_tool

CSS = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 120)
RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
STEEL = Material("steel", 1800)


class SpindleTests(unittest.TestCase):
    def test_constant_rpm_gives_a_cutting_speed_that_follows_the_radius(self):
        self.assertAlmostEqual(cutting_speed_at(RPM, 10), 2 * 3.141592653589793 * 10 * 1000 / 1000)

    def test_constant_surface_speed_gives_the_set_speed_until_the_rpm_limit(self):
        self.assertAlmostEqual(cutting_speed_at(CSS, 10), 120)
        limited = replace(CSS, rpm_limit=500)
        self.assertAlmostEqual(rpm_at(limited, 10), 500)
        self.assertLess(cutting_speed_at(limited, 10), 120)

    def test_near_the_axis_the_radius_has_a_floor(self):
        self.assertTrue(rpm_at(CSS, 0) < float("inf"))


def program(depth, feed, spindle=CSS):
    return Program(
        raw_part=RawPart("steel", 30, 60), tools=(simple_tool(1),),
        safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1),
        blocks=(TurningBlock(
            block_id="t", tool_number=1, spindle=spindle, side=TurningSide.OUTSIDE,
            target_radius_mm=15 - depth, end_z_mm=-30, feed_mm_per_rev=feed,
            depth_of_cut_mm=depth,
        ),),
    )


def machine(kw):
    return MachineDef(name="m", axes=(AxisLimits("X", -5, 80), AxisLimits("Z", -250, 10)),
                      min_rpm=50, max_rpm=3000, spindle_power_kw=kw)


class PowerTests(unittest.TestCase):
    def estimate(self, depth, feed, kw=2.2, material=STEEL):
        prog = program(depth, feed)
        return estimate_power(prog, plan_program(prog), machine(kw), material)

    def test_a_single_pass_matches_the_textbook_formula(self):
        result = self.estimate(2, 0.25)
        expected = 1800 * 2 * 0.25 * 120 / POWER_FORMULA_DIVISOR / POWER_EFFICIENCY
        self.assertAlmostEqual(result.blocks[0].required_kw, expected, delta=expected * 0.1)
        self.assertEqual(result.label, "estimate")

    def test_a_heavy_cut_is_flagged_and_a_light_one_is_not(self):
        heavy = self.estimate(3, 0.4, kw=1.0)
        light = self.estimate(0.5, 0.1, kw=1.0)
        self.assertTrue(any("needs about" in m and "estimate" in m for m in heavy.messages))
        self.assertFalse(any("needs about" in m for m in light.messages))

    def test_a_material_without_cutting_data_gives_a_warning_and_no_check(self):
        result = self.estimate(2, 0.25, material=Material("unknown"))
        self.assertFalse(result.checked)
        self.assertIn("no cutting data", result.messages[0])

    def test_an_unknown_material_name_says_so(self):
        result = self.estimate(2, 0.25, material=None)
        self.assertFalse(result.checked)
        self.assertIn("not in the material table", result.messages[0])

    def test_without_machine_power_nothing_is_compared(self):
        prog = program(2, 0.25)
        result = estimate_power(prog, plan_program(prog), replace(machine(2.2), spindle_power_kw=None), STEEL)
        self.assertTrue(result.checked)
        self.assertTrue(any("not known" in m for m in result.messages))

    def test_the_machine_check_flags_a_big_part_and_an_rpm_outside_the_limits(self):
        prog = program(2, 0.25, RPM)
        small = replace(machine(2.2), axes=(AxisLimits("X", -5, 10), AxisLimits("Z", -250, 10)), max_rpm=500)
        messages = check_against_machine(prog, plan_program(prog), small)
        self.assertTrue(any("X reach" in m for m in messages))
        self.assertTrue(any("above the maximum" in m for m in messages))
        self.assertEqual(check_against_machine(prog, plan_program(prog), machine(2.2)), [])


if __name__ == "__main__":
    unittest.main()
