"""Trim with the button held: everything the mouse crosses is trimmed at once, and the whole swipe is one step for Undo."""

import os
import sys
import unittest

from wop.core.geometry import Point
from wop.core.sketch.solver import solve
from wop.ui.sketch_constants import TOOL_CIRCLE, TOOL_LINE, TOOL_TRIM
from wop.ui.sketch_session import SketchSession

TOL = 0.5


def _line(session: SketchSession, *points: tuple[float, float]) -> None:
    session.set_tool(TOOL_LINE)
    for x, z in points:
        session.press(Point(x, z), TOL)
    session.cancel()


def _grid() -> SketchSession:
    """One long line along z (at x = 0) crossed in the middle by three short lines, at z = 10, 20 and 30."""
    session = SketchSession()
    session.snapping = False
    _line(session, (0, 0), (0, 40))
    for z in (10, 20, 30):
        _line(session, (-5, z), (5, z))
    session.set_tool(TOOL_TRIM)
    return session


def _ends(session: SketchSession, line) -> tuple[Point, Point]:
    return session.sketch.point(line.start).position, session.sketch.point(line.end).position


def _long_line_spans(session: SketchSession) -> list[tuple[float, float]]:
    spans = []
    for line in session.sketch.lines.values():
        a, b = _ends(session, line)
        if a.x == 0 and b.x == 0:
            spans.append(tuple(sorted((a.z, b.z))))
    return sorted(spans)


def _short_lines(session: SketchSession) -> list[tuple[Point, Point]]:
    return [ends for ends in (_ends(session, line) for line in session.sketch.lines.values()) if not (ends[0].x == 0 and ends[1].x == 0)]


def _swipe(session: SketchSession, *path: tuple[float, float]) -> None:
    first, *rest = path
    session.press(Point(*first), TOL)
    for x, z in rest:
        session.drag(Point(x, z), TOL)
    session.release(Point(*path[-1]), TOL)


class SwipeTests(unittest.TestCase):
    def test_a_plain_click_still_trims_one_piece_and_is_one_undo_step(self):
        session = _grid()
        _swipe(session, (0, 15))  # between the crossings at z = 10 and z = 20
        self.assertEqual(_long_line_spans(session), [(0, 10), (20, 40)])
        session.undo()
        self.assertEqual(_long_line_spans(session), [(0, 40)])

    def test_dragging_across_trims_at_once_without_waiting_for_the_button_to_come_up(self):
        session = _grid()
        session.press(Point(-3, 5), TOL)  # on nothing: the press itself trims nothing
        self.assertEqual(len(session.sketch.lines), 4)
        session.drag(Point(-3, 35), TOL)  # crosses the three short lines at x = -3, the button is still down
        self.assertEqual(len(_short_lines(session)), 3)
        for a, b in _short_lines(session):
            self.assertGreaterEqual(min(a.x, b.x), -1e-6)  # the half on the side that was crossed is gone
        self.assertEqual(session.trail, [Point(-3, 5), Point(-3, 35)])  # the path is kept to be drawn
        session.release(Point(-3, 35), TOL)
        self.assertEqual(session.trail, [])

    def test_the_whole_swipe_is_one_undo_step(self):
        session = _grid()
        before = session.sketch.signature()
        _swipe(session, (-3, 5), (-3, 15), (-3, 25), (-3, 35))
        self.assertNotEqual(session.sketch.signature(), before)
        session.undo()
        self.assertEqual(session.sketch.signature(), before)
        session.redo()
        self.assertNotEqual(session.sketch.signature(), before)

    def test_a_press_on_a_piece_trims_it_and_the_swipe_goes_on_from_there(self):
        session = _grid()
        before = session.sketch.signature()
        _swipe(session, (-3, 10), (-3, 25))  # the press is on the first short line, the path then crosses the second
        for a, b in sorted(_short_lines(session), key=lambda ends: ends[0].z)[:2]:
            self.assertGreaterEqual(min(a.x, b.x), -1e-6)
        third = max(_short_lines(session), key=lambda ends: ends[0].z)
        self.assertEqual(min(third[0].x, third[1].x), -5)  # the third was not reached
        session.undo()
        self.assertEqual(session.sketch.signature(), before)

    def test_swiping_over_nothing_changes_nothing_and_adds_no_undo_step(self):
        session = _grid()
        steps, before = len(session._undo), session.sketch.signature()
        _swipe(session, (50, 5), (50, 35))
        self.assertEqual(len(session._undo), steps)
        self.assertEqual(session.sketch.signature(), before)

    def test_a_path_through_a_corner_does_not_eat_the_lines(self):
        session = SketchSession()
        session.snapping = False
        _line(session, (0, 0), (0, 10), (10, 10))  # a corner at (0, 10)
        session.set_tool(TOOL_TRIM)
        before = session.sketch.signature()
        _swipe(session, (-3, 7), (3, 13))  # a diagonal right through the corner point
        self.assertEqual(session.sketch.signature(), before)

    def test_a_circle_that_cannot_be_trimmed_does_not_stop_the_rest(self):
        session = SketchSession()
        session.snapping = False
        session.set_tool(TOOL_CIRCLE)
        session.press(Point(0, 0), TOL)
        session.press(Point(0, 5), TOL)  # a circle of radius 5 round the origin
        session.cancel()
        _line(session, (6, -5), (6, 5))  # a line along z at x = 6
        _line(session, (3, 4), (9, 4))  # and a line across it, at z = 4
        session.set_tool(TOOL_TRIM)
        _swipe(session, (-8, 0), (8, 0))  # along x at z = 0: through the circle twice, then through the line at x = 6
        circle = next(iter(session.sketch.arcs.values()))
        self.assertTrue(session.sketch.segment(circle).is_full_circle)  # no second crossing: it stays whole
        down_the_line = [ends for ends in (_ends(session, l) for l in session.sketch.lines.values()) if ends[0].x == 6 == ends[1].x]
        self.assertEqual(len(down_the_line), 1)
        self.assertEqual(sorted(p.z for p in down_the_line[0]), [4, 5])  # the lower part, through z = 0, is gone

    def test_the_relations_still_hold_after_a_swipe(self):
        session = _grid()
        long_line = session.sketch.lines[min(session.sketch.lines)]
        session.sketch.add_constraint("vertical", (long_line.start, long_line.end))
        _swipe(session, (0, 15), (-3, 15))
        self.assertTrue(solve(session.sketch).converged)
        self.assertTrue(session.sketch.constraints)


HAVE_REAL_QT = False
try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    pass


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class SwipeWindowTests(unittest.TestCase):
    def test_holding_the_button_in_the_window_trims_and_draws_the_trail(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        from wop.ui.qt.sketch_dialog import SketchDialog

        app = QApplication.instance() or QApplication([])
        dialog = SketchDialog()
        dialog.show()
        session, canvas = dialog.session, dialog.canvas
        session.snapping = False
        _line(session, (0, 0), (0, 40))
        _line(session, (-5, 10), (5, 10))
        dialog.tool_buttons[TOOL_TRIM].click()
        start = canvas.to_screen(Point(-3, 5))
        end = canvas.to_screen(Point(-3, 15))
        QTest.mousePress(canvas, Qt.LeftButton, Qt.NoModifier, start.toPoint())
        moved = QMouseEvent(QEvent.MouseMove, end, canvas.mapToGlobal(end), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        canvas.mouseMoveEvent(moved)  # a move with the button held
        self.assertEqual(len(session.trail), 2)
        dialog.grab()  # the trail is painted
        short = _short_lines(session)
        self.assertEqual(len(short), 1)
        self.assertGreaterEqual(min(short[0][0].x, short[0][1].x), -1e-6)  # trimmed while the button is still down
        QTest.mouseRelease(canvas, Qt.LeftButton, Qt.NoModifier, end.toPoint())
        self.assertEqual(session.trail, [])
        dialog.close()
        del app


if __name__ == "__main__":
    unittest.main()
