"""The sketch canvas with the real PySide6, offscreen: Ctrl+click adds to the selection and takes from it, Shift does not."""

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
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    APP = QApplication.instance() or QApplication([])

from wop.core.geometry import Point
from wop.ui.sketch_constants import TOOL_LINE, TOOL_SELECT
from wop.ui.sketch_session import SketchSession


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class CanvasKeyTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.qt.sketch_canvas import SketchCanvas

        self.session = SketchSession()
        self.session.snapping = False
        self.session.set_tool(TOOL_LINE)
        for chain in (((0, 0), (5, 10)), ((20, 0), (25, 10))):
            for x, z in chain:
                self.session.press(Point(x, z), 0.5)
                self.session.release(Point(x, z), 0.5)
            self.session.cancel()
        self.session.set_tool(TOOL_SELECT)
        self.canvas = SketchCanvas(self.session)
        self.canvas.resize(600, 400)
        self.canvas.show()
        self.addCleanup(self.canvas.deleteLater)

    def click(self, x: float, z: float, modifier=Qt.NoModifier) -> None:
        screen = self.canvas.to_screen(Point(x, z))
        QTest.mouseClick(self.canvas, Qt.LeftButton, modifier, screen.toPoint())

    def test_ctrl_click_adds_and_takes_away_and_shift_does_not(self):
        self.click(2.5, 5)
        self.assertEqual(len(self.session.selected_pieces), 1)
        self.click(22.5, 5, Qt.ShiftModifier)  # Shift is a plain click now: the selection moves to the other line
        self.assertEqual(len(self.session.selected_pieces), 1)
        self.click(2.5, 5, Qt.ControlModifier)
        self.assertEqual(len(self.session.selected_pieces), 2)
        self.click(22.5, 5, Qt.ControlModifier)
        self.assertEqual(len(self.session.selected_pieces), 1)


if __name__ == "__main__":
    unittest.main()
