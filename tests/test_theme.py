import unittest

from wop.ui.theme import DARK_COLORS, LIGHT_COLORS, _luminance, color_set_for, is_dark, mix_colors

MIN_CONTRAST = 0.3  # brightness difference (0..1) between a drawing colour and its background


class ColorSetTests(unittest.TestCase):
    def test_a_dark_window_gets_the_dark_set_and_a_light_window_the_light_set(self):
        self.assertEqual(color_set_for("#202020", "#ffffff").block_colors, DARK_COLORS.block_colors)
        self.assertEqual(color_set_for("#f0f0f0", "#000000").block_colors, LIGHT_COLORS.block_colors)

    def test_the_set_for_a_window_has_no_background_and_takes_the_window_text_colour(self):
        chosen = color_set_for("#202020", "#abcdef")
        self.assertIsNone(chosen.background)
        self.assertEqual(chosen.text, "#abcdef")

    def test_the_sets_for_files_have_a_background(self):
        self.assertTrue(LIGHT_COLORS.background)
        self.assertTrue(DARK_COLORS.background)

    def test_unusable_colours_give_the_light_set_without_background(self):
        chosen = color_set_for("nonsense", "x")
        self.assertEqual(chosen.block_colors, LIGHT_COLORS.block_colors)
        self.assertIsNone(chosen.background)
        self.assertEqual(chosen.text, LIGHT_COLORS.text)

    def test_brightness(self):
        self.assertTrue(is_dark("#000000"))
        self.assertFalse(is_dark("#ffffff"))
        self.assertAlmostEqual(_luminance("#ffffff"), 1.0)
        with self.assertRaises(ValueError):
            _luminance("#fff")

    def test_every_drawing_colour_can_be_read_on_the_background_of_its_set(self):
        for colors in (LIGHT_COLORS, DARK_COLORS):
            background = _luminance(colors.background)
            drawn = (*colors.block_colors, colors.rapid, colors.finding, colors.key_text, colors.text,
                     colors.cut_3d, colors.rapid_3d)
            for color in drawn:
                self.assertGreater(abs(_luminance(color) - background), MIN_CONTRAST, color)

    def test_both_sets_have_the_same_number_of_block_colours(self):
        self.assertEqual(len(LIGHT_COLORS.block_colors), len(DARK_COLORS.block_colors))


if __name__ == "__main__":
    unittest.main()


class MixColorsTests(unittest.TestCase):
    def test_the_ends_and_the_middle(self):
        self.assertEqual(mix_colors("#000000", "#ffffff", 0), "#000000")
        self.assertEqual(mix_colors("#000000", "#ffffff", 1), "#ffffff")
        self.assertEqual(mix_colors("#000000", "#ffffff", 0.5), "#808080")

    def test_a_faded_text_stays_between_text_and_field_colour(self):
        for text, field in (("#202020", "#ffffff"), ("#e0e0e0", "#1e1e1e")):
            faded = _luminance(mix_colors(text, field, 0.55))
            low, high = sorted((_luminance(text), _luminance(field)))
            self.assertTrue(low < faded < high)

    def test_a_bad_colour_is_refused(self):
        with self.assertRaises(ValueError):
            mix_colors("red", "#ffffff", 0.5)
