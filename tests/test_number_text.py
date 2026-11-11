import unittest

from wop.ui.number_text import number_from_text


class NumberTextTests(unittest.TestCase):
    def test_plain_numbers_with_point_or_comma(self):
        for text, value in (("12", 12), ("12.5", 12.5), ("12,5", 12.5), ("-3.25", -3.25), (".5", 0.5), ("+2", 2)):
            with self.subTest(text=text):
                self.assertEqual(number_from_text(text), value)

    def test_the_unit_after_the_number_does_not_matter(self):
        for text, value in (("12.5 mm", 12.5), ("0.2 mm/rev", 0.2), ("1000 RPM", 1000), ("-4,5 deg", -4.5)):
            with self.subTest(text=text):
                self.assertEqual(number_from_text(text), value)

    def test_text_without_a_number_gives_none(self):
        for text in ("", "mm", "-", " "):
            self.assertIsNone(number_from_text(text))


if __name__ == "__main__":
    unittest.main()
