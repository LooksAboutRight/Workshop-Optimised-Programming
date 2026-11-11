import unittest

from wop.core.tooling.insert_designation import DesignationError, parse_designation


class DesignationTests(unittest.TestCase):
    def test_cnmg_120408_is_an_80_degree_diamond_with_08_radius(self):
        d = parse_designation("CNMG 120408")
        self.assertEqual((d.tip_angle_deg, d.nose_radius_mm, d.thickness_mm), (80, 0.8, 4.76))
        self.assertAlmostEqual(d.inscribed_circle_mm, 12.7)
        self.assertAlmostEqual(d.edge_length_mm, 12.7 / 0.984808, places=3)
        self.assertEqual(d.text, "CNMG 120408")

    def test_spaces_case_and_the_manufacturer_code_do_not_matter(self):
        d = parse_designation("cnmg12 04 08e r-pm")
        self.assertEqual((d.text, d.edge_preparation, d.hand, d.manufacturer), ("CNMG 120408ER-PM", "rounded edge", "right hand", "PM"))

    def test_well_known_designations_are_accepted(self):
        for text in ("CNMG 120404", "CNMG 120412", "DNMG 150608", "DNMG 110408", "TNMG 160408", "TNMG 220412",
                     "VNMG 160408", "SNMG 120408", "CCMT 060204", "CNMG 160616", "CCMT 09T308"):
            with self.subTest(text=text):
                parse_designation(text)

    def test_a_wrong_designation_names_the_position(self):
        for text, position in (("XNMG 120408", 1), ("CXMG 120408", 2), ("CNXG 120408", 3), ("CNMZ 120408", 4),
                               ("CNMG 130408", 5), ("CNMG 120808", 6), ("CNMG 120409", 7), ("1NMG 120408", 1),
                               ("CNMG 1204", 7), ("CN", 3), ("", 1)):
            with self.subTest(text=text):
                with self.assertRaises(DesignationError) as caught:
                    parse_designation(text)
                self.assertEqual(caught.exception.position, position, str(caught.exception))

    def test_a_shape_that_is_not_supported_yet_says_so(self):
        with self.assertRaises(DesignationError) as caught:
            parse_designation("RNMG 120400")
        self.assertIn("not supported", str(caught.exception))

    def test_the_decoded_lines_name_every_position(self):
        text = "\n".join(parse_designation("CNMG 120408").lines())
        for word in ("Shape", "Clearance", "Tolerance", "Type", "Size", "Thickness", "Corner radius"):
            self.assertIn(word, text)

    def test_trailing_rubbish_is_refused(self):
        with self.assertRaises(DesignationError):
            parse_designation("CNMG 120408 xyz!")


if __name__ == "__main__":
    unittest.main()
