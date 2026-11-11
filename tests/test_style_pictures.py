"""The pictures of the block styles: the SVG made from a style, and the dropdown that shows them when an entry is hovered."""

import os
import sys
import unittest


try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    APP = QApplication.instance() or QApplication([])

from wop.adapters.style_samples import samples_for
from wop.ui.style_picture import style_pictures
from wop.ui.theme import LIGHT_COLORS


class StylePictureTests(unittest.TestCase):
    def test_there_is_one_picture_for_every_sample_and_the_styles_look_different(self):
        standard = style_pictures("grooving", "standard", LIGHT_COLORS)
        layers = style_pictures("grooving", "layers", LIGHT_COLORS)
        self.assertEqual([p.caption for p in standard], [s.name for s in samples_for("grooving")])
        for first, second in zip(standard, layers):
            self.assertTrue(first.svg.startswith("<svg") and second.svg.startswith("<svg"))
            self.assertEqual(first.problem, "")
        deep = lambda pictures: next(p for p in pictures if "deep" in p.caption).svg
        self.assertNotEqual(deep(standard), deep(layers))
        self.assertGreater(deep(layers).count("<polyline"), deep(standard).count("<polyline"))

    def test_only_cutting_moves_are_drawn_and_in_the_colours_of_their_order(self):
        svg = style_pictures("grooving", "standard", LIGHT_COLORS)[0].svg
        self.assertNotIn("stroke-dasharray=\"15", svg)  # no dashed rapid lines (the dashes of the other lines are not these)
        self.assertIn("#2f80ff", svg)  # the first cutting move
        self.assertIn("#ff5a1f", svg)  # the last one

    def test_a_style_that_is_not_loaded_gives_the_reason_instead_of_a_picture(self):
        pictures = style_pictures("grooving", "not_there", LIGHT_COLORS)
        self.assertTrue(all(p.svg == "" and "not available" in p.problem for p in pictures))


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class StyleComboTests(unittest.TestCase):
    def test_hovering_an_entry_shows_its_pictures_and_closing_the_list_hides_them(self):
        from wop.ui.qt.style_preview import StyleCombo

        combo = StyleCombo("grooving")
        self.addCleanup(combo.deleteLater)
        for key, label in (("standard", "Standard"), ("layers", "Layers")):
            combo.addItem(label, key)
        combo.show()
        combo.showPopup()
        APP.processEvents()
        combo._hovered(combo.model().index(1, 0))
        self.assertTrue(combo._preview.isVisible())
        labels = [label.text() for label in combo._preview.findChildren(type(combo._preview._layout.itemAt(0).widget()))]
        self.assertIn("Layers", labels)
        self.assertIn("outside, narrow groove", labels)
        combo.hidePopup()
        self.assertFalse(combo._preview.isVisible())

    def test_the_form_uses_the_picture_dropdown_for_the_style_field_only(self):
        from wop.adapters.style_samples import samples_for as samples
        from wop.ui.block_forms import form_for

        block, _context = samples("grooving")[0].build("layers")
        previews = {spec.path[0]: spec.preview for spec in form_for(block)}
        self.assertEqual(previews["style"], "grooving")
        self.assertEqual([name for name, shown in previews.items() if shown], ["style"])


if __name__ == "__main__":
    unittest.main()
