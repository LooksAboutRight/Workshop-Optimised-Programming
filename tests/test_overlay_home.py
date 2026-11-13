"""The 2D picture opens on the home rectangle (the part) and can be zoomed out to the whole picture (real PySide6, skipped without it)."""

import os
import unittest

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QByteArray
    from PySide6.QtWidgets import QApplication

    APP = QApplication.instance() or QApplication([])
except ImportError:  # no PySide6 here
    APP = None

from wop.core.program_model.program import plan_program
from wop.ui.svg_preview import render_svg, svg_home
from tests import svg_demo


@unittest.skipIf(APP is None, "needs PySide6")
class OverlayHomeTests(unittest.TestCase):
    def widget(self):
        from wop.ui.qt.overlay_svg import OverlaySvgWidget

        text = render_svg(plan_program(svg_demo.outside_program()), with_legend=False, whole=True)
        widget = OverlaySvgWidget()
        widget.resize(800, 500)
        widget.set_home(svg_home(text))
        widget.load(QByteArray(text.encode("utf-8")))
        return widget

    def test_the_home_view_fills_the_widget_and_zooming_out_shows_everything(self):
        widget = self.widget()
        x, y, width, height = widget._base_rect()
        home = widget._home
        scale = min(800 / home[2], 500 / home[3])
        self.assertAlmostEqual(width, widget.renderer().defaultSize().width() * scale)
        self.assertLess(widget._min_zoom(), 1)
        self.assertAlmostEqual(widget.line_scale(), widget._min_zoom())  # lines as thick as in the whole picture
        widget._view.zoom_at((400, 250), widget._base_rect(), 1e-6, widget._window_rect(), widget._min_zoom())
        widget._centre_whole()
        left, top, whole_width, whole_height = widget._view.view_rect(widget._base_rect())
        self.assertLessEqual(whole_width, 800 + 1e-6)
        self.assertLessEqual(whole_height, 500 + 1e-6)
        self.assertGreaterEqual(left, -1e-6)
        self.assertGreaterEqual(top, -1e-6)

    def test_reset_returns_to_home(self):
        widget = self.widget()
        widget._view.zoom_at((100, 100), widget._base_rect(), 3.0, widget._window_rect(), widget._min_zoom())
        widget.reset_view()
        self.assertTrue(widget._view.is_default)


if __name__ == "__main__":
    unittest.main()
