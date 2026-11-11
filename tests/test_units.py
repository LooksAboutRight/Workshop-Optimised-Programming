import unittest

from wop.core.constants import MM_PER_INCH
from wop.core.program_model.units import UnitSystem, length_from_mm, length_to_mm

ALL_UNITS = (UnitSystem.METRIC, UnitSystem.IMPERIAL)


class LengthTests(unittest.TestCase):
    def test_metric_is_unchanged(self):
        self.assertEqual(length_to_mm(12.5, UnitSystem.METRIC), 12.5)
        self.assertEqual(length_from_mm(12.5, UnitSystem.METRIC), 12.5)

    def test_one_inch_is_25_4_mm(self):
        self.assertAlmostEqual(length_to_mm(1, UnitSystem.IMPERIAL), MM_PER_INCH)
        self.assertAlmostEqual(length_from_mm(MM_PER_INCH, UnitSystem.IMPERIAL), 1)

    def test_round_trip(self):
        for unit in ALL_UNITS:
            self.assertAlmostEqual(length_from_mm(length_to_mm(3.75, unit), unit), 3.75)


if __name__ == "__main__":
    unittest.main()
