import unittest

from wop.core.program_model.raw_part import RawPart
from wop.core.program_model.stock import stock_region


class StockTests(unittest.TestCase):
    def test_solid_bar(self):
        region = stock_region(RawPart("steel", 30, 50))
        self.assertAlmostEqual(region.area, 15 * 50)
        bounds = region.bounds
        self.assertEqual((bounds.min_x, bounds.min_z, bounds.max_x, bounds.max_z), (0, -50, 15, 0))

    def test_tube(self):
        region = stock_region(RawPart("steel", 30, 50, inner_diameter_mm=10))
        self.assertAlmostEqual(region.area, 10 * 50)
        self.assertEqual(region.bounds.min_x, 5)


if __name__ == "__main__":
    unittest.main()
