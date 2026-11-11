import unittest

from wop.core.program_model.raw_part import RawPart, RawPartError


class RawPartTests(unittest.TestCase):
    def test_solid_bar_geometry(self):
        part = RawPart("steel", 30, 50)
        self.assertEqual(part.outer_radius_mm, 15)
        self.assertEqual(part.inner_radius_mm, 0)
        self.assertEqual(part.front_z_mm, 0)
        self.assertEqual(part.clamp_z_mm, -50)
        self.assertIsNone(part.length_inside_mm)

    def test_tube_and_front_position(self):
        part = RawPart("alu", 40, 30, inner_diameter_mm=10, front_z_mm=2)
        self.assertEqual(part.inner_radius_mm, 5)
        self.assertEqual(part.clamp_z_mm, -28)

    def test_invalid_data_is_rejected(self):
        bad = [
            dict(outer_diameter_mm=0, length_outside_mm=10),
            dict(outer_diameter_mm=10, length_outside_mm=0),
            dict(outer_diameter_mm=10, length_outside_mm=10, inner_diameter_mm=-1),
            dict(outer_diameter_mm=10, length_outside_mm=10, inner_diameter_mm=10),
            dict(outer_diameter_mm=10, length_outside_mm=10, length_mm=0),
        ]
        for arguments in bad:
            with self.subTest(arguments=arguments):
                with self.assertRaises(RawPartError):
                    RawPart("steel", **arguments)


if __name__ == "__main__":
    unittest.main()
