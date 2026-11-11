"""The fastest move of the X and Z axes: ini, form, file and the feed check."""

import unittest
from dataclasses import replace
from pathlib import Path

from wop.adapters.linuxcnc_ini import machine_from_ini_text, read_machine_from_ini
from wop.core.geometry import Point
from wop.core.program_model.operations import Rapid
from wop.core.lathe.machine import AxisLimits, MachineDef, MachineError, check_feed_speed
from wop.core.files.machine_io import machine_from_dict, machine_to_dict
from wop.ui.machine_form import form_from_machine, machine_from_form, touched_form_fields

from tests.reference_program import reference_program
from wop.core.lathe.machine_check import check_against_machine
from wop.core.program_model.program import plan_program

INI = Path(__file__).parent / "data" / "schaublin_125.ini"


class SimpleNamespaceProgram:
    class raw_part:
        outer_diameter_mm = 10
        length_outside_mm = 10


class SimpleNamespacePlan:
    def __init__(self, blocks):
        self.blocks = blocks


class DataTests(unittest.TestCase):
    def test_the_ini_gives_the_axis_velocities_in_mm_per_minute(self):
        reading = read_machine_from_ini(INI)  # [AXIS_X] and [AXIS_Z] MAX_VELOCITY = 50 mm/s
        self.assertEqual((reading.machine.max_velocity_x_mm_min, reading.machine.max_velocity_z_mm_min), (3000, 3000))
        self.assertTrue({"max_velocity_x_mm_min", "max_velocity_z_mm_min"} <= reading.found)

    def test_inch_units_are_converted_and_a_missing_value_is_noted(self):
        text = "[TRAJ]\nLINEAR_UNITS = inch\n[AXIS_X]\nMAX_VELOCITY = 1\n"
        reading = machine_from_ini_text(text, "m")
        self.assertAlmostEqual(reading.machine.max_velocity_x_mm_min, 25.4 * 60)
        self.assertIsNone(reading.machine.max_velocity_z_mm_min)
        self.assertTrue(any("axis Z" in note and "velocity" in note for note in reading.notes))
        self.assertNotIn("max_velocity_z_mm_min", reading.found)

    def test_a_velocity_must_be_positive(self):
        with self.assertRaises(MachineError):
            MachineDef("m", max_velocity_x_mm_min=0)

    def test_file_and_form_keep_the_values_and_old_files_still_load(self):
        machine = MachineDef("m", max_velocity_x_mm_min=1500, max_velocity_z_mm_min=3000)
        self.assertEqual(machine_from_dict(machine_to_dict(machine)), machine)
        old = machine_to_dict(machine)
        del old["max_velocity_x_mm_min"], old["max_velocity_z_mm_min"]
        self.assertIsNone(machine_from_dict(old).max_velocity_x_mm_min)
        form = form_from_machine(machine)
        self.assertEqual((form.x_max_velocity_mm_min, form.z_max_velocity_mm_min), (1500, 3000))
        self.assertEqual(machine_from_form(replace(form, z_max_velocity_mm_min=900)).max_velocity_z_mm_min, 900)
        self.assertEqual(touched_form_fields(frozenset({"max_velocity_x_mm_min"}), machine), ("x_max_velocity_mm_min",))

    def test_the_speed_check_splits_a_move_between_the_axes(self):
        machine = MachineDef("m", max_velocity_x_mm_min=500, max_velocity_z_mm_min=2000)
        self.assertEqual(check_feed_speed(machine, 600, 0.0, 1.0), [])  # along Z only: fine
        found = check_feed_speed(machine, 600, 1.0, 0.0)  # along X: too fast
        self.assertEqual(len(found), 1)
        self.assertIn("along X", found[0])
        self.assertEqual(check_feed_speed(MachineDef("m"), 1e9, 1.0, 1.0), [])  # unknown: not checked


class ProgramCheckTests(unittest.TestCase):
    def setUp(self):
        self.program = reference_program()
        self.plan = plan_program(self.program)
        self.machine = MachineDef("m", axes=(AxisLimits("X", -5, 100), AxisLimits("Z", -300, 10)), min_rpm=50, max_rpm=3000,
                                  spindle_power_kw=5.5)

    def messages(self, **velocities):
        found = check_against_machine(self.program, self.plan, replace(self.machine, **velocities))
        return [m for m in found if "mm/min" in m]

    def test_nothing_is_said_when_the_velocities_are_not_known_or_high(self):
        self.assertEqual(self.messages(), [])
        self.assertEqual(self.messages(max_velocity_x_mm_min=1e6, max_velocity_z_mm_min=1e6), [])

    def test_a_slow_axis_is_reported_per_block_with_the_remedy(self):
        found = self.messages(max_velocity_x_mm_min=1, max_velocity_z_mm_min=1)
        self.assertTrue(found)
        self.assertTrue(all(m.startswith("block ") and "mm/rev at" in m and "lower the feed" in m for m in found))
        self.assertEqual(len({m.split(" ")[1] for m in found}), len(found))  # one message per block


class EveryMoveWithAnRpmTests(unittest.TestCase):
    """Drilling and thread passes are checked like any feed move, and so is a speed set in the middle of a block."""

    def setUp(self):
        from types import SimpleNamespace

        from wop.core.program_model.operations import SpindleMode, SpindleSetting

        self.rpm = lambda value: SpindleSetting(SpindleMode.CONSTANT_RPM, value)
        self.plan = lambda setting, *ops: SimpleNamespace(block=SimpleNamespace(spindle=setting), operations=ops)
        self.machine = MachineDef("m", max_velocity_z_mm_min=3000)

    def test_a_drill_feed_is_checked_along_z(self):
        from wop.core.lathe.machine_check import _feed_too_fast
        from wop.core.program_model.operations import DrillOperation

        drill = DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.2)
        self.assertEqual(_feed_too_fast(self.plan(self.rpm(1000), drill), self.machine), "")  # 200 mm/min
        self.assertIn("0.2 mm/rev at 20000 RPM", _feed_too_fast(self.plan(self.rpm(20000), drill), self.machine))  # 4000 mm/min

    def test_a_thread_feed_is_pitch_times_rpm(self):
        from wop.core.lathe.machine_check import _feed_too_fast
        from wop.core.program_model.operations import ThreadOperation

        thread = ThreadOperation(10, 2, -20, 3.0, -1.8, 0.3, 1.8, 2.0, 29.5, 1)
        self.assertEqual(_feed_too_fast(self.plan(self.rpm(900), thread), self.machine), "")  # 2700 mm/min
        self.assertIn("3 mm/rev at 1500 RPM", _feed_too_fast(self.plan(self.rpm(1500), thread), self.machine))  # 4500 mm/min

    def test_a_speed_set_in_the_block_counts_for_the_moves_after_it(self):
        from wop.core.lathe.machine_check import _feed_too_fast
        from wop.core.program_model.operations import LinearMove, SetSpindle

        ops = (Rapid(Point(10, 5)), SetSpindle(self.rpm(4000)), LinearMove(Point(10, -5), 1.0))  # 4000 mm/min along Z
        self.assertIn("1 mm/rev at 4000 RPM", _feed_too_fast(self.plan(self.rpm(100), *ops), self.machine))

    def test_the_machine_maximum_rpm_is_checked_for_a_speed_set_in_the_block(self):
        from wop.core.lathe.machine_check import check_against_machine
        from wop.core.program_model.operations import SetSpindle

        machine = MachineDef("m", max_rpm=3000)
        plan = self.plan(self.rpm(1000), SetSpindle(self.rpm(5000)))
        plan.number = 1
        plan.block.type_name = "turning"
        plan.block.coolant = None
        plan.block.required_capabilities = frozenset()
        program = SimpleNamespaceProgram()
        found = check_against_machine(program, SimpleNamespacePlan([plan]), machine)
        self.assertTrue(any("5000 RPM is above the maximum" in m for m in found))


if __name__ == "__main__":
    unittest.main()
