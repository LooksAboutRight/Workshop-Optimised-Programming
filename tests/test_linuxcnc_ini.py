import tempfile
import unittest
from pathlib import Path

from wop.adapters.linuxcnc_ini import IniError, machine_from_ini_text, read_machine_from_ini
from wop.core.program_model.units import UnitSystem, XInputMode

SAMPLE_INI = """\
# sample lathe
[DISPLAY]
DISPLAY = gmoccapy
LATHE = 1

[RS274NGC]
RS274NGC_STARTUP_CODE = G18 G21 G40 G7 G90 G94 ; lathe start

[TRAJ]
COORDINATES = X Z
LINEAR_UNITS = mm

[SPINDLE_0]
MIN_FORWARD_VELOCITY = 50
MAX_FORWARD_VELOCITY = 3000

[AXIS_X]
MIN_LIMIT = -5.0
MAX_LIMIT = 100.0

[AXIS_Z]
MIN_LIMIT = -300.0
MAX_LIMIT = 10.0
"""


class IniTests(unittest.TestCase):
    """Requirement M2 and M6."""

    def test_sample_ini_fills_in_what_it_holds(self):
        reading = machine_from_ini_text(SAMPLE_INI, "sample")
        machine = reading.machine
        self.assertEqual(machine.unit_system, UnitSystem.METRIC)
        self.assertEqual(machine.default_x_mode, XInputMode.DIAMETER)
        self.assertEqual(machine.axis("X").max_mm, 100)
        self.assertEqual(machine.axis("Z").min_mm, -300)
        self.assertEqual((machine.min_rpm, machine.max_rpm), (50, 3000))

    def test_what_is_not_in_the_ini_is_asked_for(self):
        reading = machine_from_ini_text(SAMPLE_INI, "sample")
        self.assertEqual(reading.machine.missing_values(), ["spindle power"])
        self.assertTrue(any("spindle power" in note for note in reading.notes))

    def test_imperial_ini_gives_imperial_and_millimetre_limits(self):
        text = SAMPLE_INI.replace("LINEAR_UNITS = mm", "LINEAR_UNITS = inch")
        machine = machine_from_ini_text(text, "imp").machine
        self.assertEqual(machine.unit_system, UnitSystem.IMPERIAL)
        self.assertAlmostEqual(machine.axis("X").max_mm, 2540)

    def test_radius_mode_from_startup_code(self):
        text = SAMPLE_INI.replace("G7 ", "G8 ")
        self.assertEqual(machine_from_ini_text(text, "m").machine.default_x_mode, XInputMode.RADIUS)

    def test_empty_ini_gives_notes_and_missing_values(self):
        reading = machine_from_ini_text("[EMC]\nVERSION = 1.1\n", "empty")
        self.assertEqual(len(reading.machine.missing_values()), 5)
        self.assertGreaterEqual(len(reading.notes), 4)

    def test_file_without_section_header_is_an_error(self):
        with self.assertRaises(IniError):
            machine_from_ini_text("KEY = value\n", "bad")

    def test_read_from_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mylathe.ini"
            path.write_text(SAMPLE_INI, encoding="utf-8")
            reading = read_machine_from_ini(path)
        self.assertEqual(reading.machine.name, "mylathe")

    def test_coordinates_without_a_space(self):
        text = SAMPLE_INI.replace("COORDINATES = X Z", "COORDINATES = XZ")
        self.assertEqual(machine_from_ini_text(text, "m").machine.missing_values(), ["spindle power"])


class RealIniTests(unittest.TestCase):
    """The ini of the Schaublin 125 CNC (LinuxCNC 2.9, written by PNCconf)."""

    def test_schaublin_ini(self):
        path = Path(__file__).parent / "data" / "schaublin_125.ini"
        reading = read_machine_from_ini(path)
        machine = reading.machine
        self.assertEqual(machine.unit_system, UnitSystem.METRIC)
        self.assertEqual(machine.default_x_mode, XInputMode.DIAMETER)  # startup code has G7
        self.assertEqual((machine.axis("X").min_mm, machine.axis("X").max_mm), (-81, 104))
        self.assertEqual((machine.axis("Z").min_mm, machine.axis("Z").max_mm), (-400, 0.1))
        self.assertEqual((machine.min_rpm, machine.max_rpm), (60, 3000))
        self.assertEqual(machine.missing_values(), ["spindle power"])


if __name__ == "__main__":
    unittest.main()
