"""Placed dimensions can be moved, but only the way their kind allows; they are drawn under the sketch, numbers clear of lines."""

import math
import os
import sys
import unittest

from wop.core.geometry import Point
from wop.ui.sketch_constants import TOOL_DIMENSION, TOOL_LINE, TOOL_SELECT
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_text_place import box_hits_segment

TOL = 0.5


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)


def _with_dimension(points, pick, place, kind_expected) -> tuple[SketchSession, object]:
    """A sketch of one line through `points` with a dimension placed at `place` after picking `pick`."""
    session = SketchSession()
    session.snapping = False
    session.set_tool(TOOL_LINE)
    for x, z in points:
        session.press(Point(x, z), TOL)
    session.cancel()
    session.set_tool(TOOL_DIMENSION)
    for x, z in pick:
        _click(session, x, z)
    _click(session, *place)
    (constraint,) = [c for c in session.sketch.constraints.values()]
    assert constraint.kind == kind_expected, constraint.kind
    session.set_tool(TOOL_SELECT)
    return session, constraint


def _drag(session: SketchSession, start: Point, *path: Point) -> None:
    session.press(start, TOL)
    for point in path:
        session.drag(point, TOL)
    session.release(path[-1] if path else start, TOL)


def _offset(session: SketchSession, constraint) -> tuple[float, float]:
    return session.sketch.constraints[constraint.constraint_id].offset


class MovingTests(unittest.TestCase):
    def test_a_dimension_along_z_moves_only_up_and_down(self):
        session, constraint = _with_dimension([(0, 0), (4, 20)], [(2, 10)], (-10, 10), "distance_z")  # line below the points
        before = _offset(session, constraint)
        _drag(session, Point(-10, 5), Point(-12, 9), Point(-15, 14))  # on the dimension line, dragged up and to the side
        after = _offset(session, constraint)
        self.assertAlmostEqual(after[0], before[0] - 5)  # it followed in x (the direction of the dimension line's normal)
        self.assertAlmostEqual(after[1], before[1])  # but not in z: the sideways part of the mouse movement is ignored

    def test_a_dimension_along_x_moves_only_sideways(self):
        session, constraint = _with_dimension([(0, 0), (20, 4)], [(10, 2)], (10, 30), "distance_x")
        before = _offset(session, constraint)
        _drag(session, Point(10, 30), Point(14, 33), Point(18, 38))  # up and to the right
        after = _offset(session, constraint)
        self.assertAlmostEqual(after[1], before[1] + 8)
        self.assertAlmostEqual(after[0], before[0])

    def test_a_length_moves_only_square_to_its_line(self):
        session, constraint = _with_dimension([(0, 0), (0, 20)], [(0, 10)], (2, 10), "length")  # a line along z
        before = _offset(session, constraint)
        _drag(session, Point(2, 10), Point(4, 14), Point(6, 18))
        after = _offset(session, constraint)
        self.assertAlmostEqual(after[0], before[0] + 4)  # away from the line (x), not along it
        self.assertAlmostEqual(after[1], before[1])

    def test_a_length_of_a_sloped_line_moves_along_its_normal(self):
        session, constraint = _with_dimension([(0, 0), (10, 10)], [(5, 5)], (7, 3), "length")
        before = _offset(session, constraint)
        _drag(session, Point(7, 3), Point(9, 1))  # straight along the normal (+x, -z) of a line that runs (+x, +z)
        after = _offset(session, constraint)
        moved = (after[0] - before[0], after[1] - before[1])
        self.assertAlmostEqual(moved[0], -moved[1])  # along the normal ...
        self.assertAlmostEqual(math.hypot(*moved), math.hypot(2, 2))  # ... all of it
        _drag(session, Point(9, 1), Point(10, 2))  # now along the line: nothing moves
        again = _offset(session, constraint)
        self.assertAlmostEqual(again[0], after[0])
        self.assertAlmostEqual(again[1], after[1])

    def test_a_diameter_moves_any_way(self):
        session = SketchSession()
        session.snapping = False
        circle_centre, edge = session.sketch.add_point(0, 0), session.sketch.add_point(0, 5)
        session.sketch.add_arc(circle_centre, edge, edge)
        session.set_tool(TOOL_DIMENSION)
        _click(session, 5, 0)
        _click(session, 12, 9)
        (constraint,) = session.sketch.constraints.values()
        session.set_tool(TOOL_SELECT)
        before = _offset(session, constraint)
        _drag(session, Point(12, 9), Point(14, 12))
        after = _offset(session, constraint)
        self.assertAlmostEqual(after[0], before[0] + 2)
        self.assertAlmostEqual(after[1], before[1] + 3)

    def test_the_value_does_not_change_and_the_whole_drag_is_one_undo_step(self):
        session, constraint = _with_dimension([(0, 0), (0, 20)], [(0, 10)], (2, 10), "length")
        offset, values, steps = _offset(session, constraint), constraint.values, len(session._undo)
        _drag(session, Point(2, 10), Point(3, 10), Point(4, 10), Point(5, 10))
        self.assertEqual(session.sketch.constraints[constraint.constraint_id].values, values)
        self.assertEqual(len(session._undo), steps + 1)
        session.undo()
        self.assertEqual(_offset(session, constraint), offset)

    def test_a_click_without_moving_changes_nothing_and_adds_no_undo_step(self):
        session, constraint = _with_dimension([(0, 0), (0, 20)], [(0, 10)], (2, 10), "length")
        steps, offset = len(session._undo), _offset(session, constraint)
        _drag(session, Point(2, 10))
        self.assertEqual((len(session._undo), _offset(session, constraint)), (steps, offset))
        self.assertEqual(session.selected_constraint, constraint.constraint_id)  # but it is chosen

    def test_a_point_close_to_the_dimension_line_wins_over_it(self):
        session, constraint = _with_dimension([(0, 0), (0, 20)], [(0, 10)], (2, 10), "length")
        session.press(Point(0, 0), TOL)  # the start of the line: also where an extension line starts
        self.assertEqual(session.selected_points, {min(session.sketch.points)})
        session.release(Point(0, 0), TOL)

    def test_the_dimension_is_found_by_its_extension_line_too_and_empty_space_is_not_a_dimension(self):
        session, constraint = _with_dimension([(0, 0), (0, 20)], [(0, 10)], (2, 10), "length")
        self.assertEqual(session.dimension_at(Point(2, 10), TOL), constraint.constraint_id)  # the dimension line
        self.assertEqual(session.dimension_at(Point(1, 20), TOL), constraint.constraint_id)  # an extension line
        self.assertIsNone(session.dimension_at(Point(40, 40), TOL))

    def test_it_is_saved_where_it_was_moved(self):
        import json

        from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict

        session, constraint = _with_dimension([(0, 0), (0, 20)], [(0, 10)], (2, 10), "length")
        _drag(session, Point(2, 10), Point(6, 10))
        again = sketch_from_dict(json.loads(json.dumps(sketch_to_dict(session.sketch))))
        self.assertEqual(next(iter(again.constraints.values())).offset, _offset(session, constraint))


HAVE_REAL_QT = False
try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    pass


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class PaintTests(unittest.TestCase):
    def _dialog(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from wop.ui.qt.sketch_dialog import SketchDialog

        app = QApplication.instance() or QApplication([])
        dialog = SketchDialog()
        dialog.resize(900, 600)
        dialog.show()
        dialog.canvas.scale = 8
        return app, dialog

    def _crossing_sketch(self, dialog) -> SketchSession:
        """A line along x (up on the screen) with a dimension along x, and a long model line that crosses its dimension line."""
        session = dialog.session
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((0, -10), (20, -10)):  # the line to measure: along x, at z = -10
            session.press(Point(x, z), TOL)
        session.cancel()
        for x, z in ((10, -30), (10, 30)):  # across the picture at x = 10: crosses the dimension line at z = 5
            session.press(Point(x, z), TOL)
        session.cancel()
        session.set_tool(TOOL_DIMENSION)
        _click(session, 4, -10)  # the first line (away from where the long line crosses it)
        _click(session, 14, 5)  # placed to the side at z = 5 (away from the long line): along X
        return session

    def test_the_model_line_is_painted_over_the_dimension_line(self):
        app, dialog = self._dialog()
        session = self._crossing_sketch(dialog)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        session.set_tool(TOOL_SELECT)
        session.selected_constraint = None
        canvas = dialog.canvas
        image = canvas.grab().toImage()
        crossing = canvas.to_screen(Point(10, 5))  # where the long model line crosses the dimension line (the number is elsewhere)
        pixels = [image.pixelColor(int(crossing.x()) + dx, int(crossing.y()) + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        self.assertTrue(any(p.blue() > 150 and p.red() < 130 for p in pixels), [p.getRgb() for p in pixels])  # the blue piece shows
        along = canvas.to_screen(Point(3, 5))  # a place on the dimension line away from the model lines
        line_pixels = [image.pixelColor(int(along.x()) + dx, int(along.y()) + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        self.assertTrue(any(p.red() < 200 and abs(p.blue() - p.red()) < 30 for p in line_pixels))  # the dimension line itself: grey or dark
        del constraint, app

    def test_a_number_keeps_clear_of_every_line_when_there_is_room(self):
        app, dialog = self._dialog()
        session = self._crossing_sketch(dialog)
        canvas = dialog.canvas
        canvas.grab()
        (rect, _id) = next((r, i) for r, i in canvas._tag_rects)
        box = (rect.left() + 2, rect.top() + 2, rect.width() - 4, rect.height() - 4)
        lines = canvas._obstacles(canvas._dimension_drawings(canvas.palette().text().color(), canvas.palette().highlight().color()))
        for line in lines:
            for a, b in line:
                self.assertFalse(box_hits_segment(box, a, b), (box, a, b))
        del session, app

    def test_the_sharp_corner_left_by_a_fillet_is_drawn_dashed_and_thin_and_the_outline_is_not(self):
        from unittest import mock

        app, dialog = self._dialog()
        session = dialog.session
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (0, 20), (20, 20)):
            session.press(Point(x, z), TOL)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        _click(session, 0, 20)
        self.assertTrue(session.apply_corner("fillet", 3))
        session.selected_points = set()
        calls = []
        canvas = dialog.canvas
        real = canvas._paint_segment

        def record(painter, segment, colour, dashed, width=2, centre=False):
            calls.append((dashed, width))
            return real(painter, segment, colour, dashed, width, centre)

        with mock.patch.object(canvas, "_paint_segment", record):
            canvas.grab()
        self.assertEqual(sorted(w for dashed, w in calls if dashed), [1, 1])  # the two reference lines: dashed and one pixel
        self.assertEqual(sorted(w for dashed, w in calls if not dashed), [2, 2, 2])  # new line, arc, new line: full lines
        del app

    def test_a_dimension_can_be_moved_with_the_mouse_in_the_window(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        app, dialog = self._dialog()
        session = self._crossing_sketch(dialog)
        session.set_tool(TOOL_SELECT)
        canvas = dialog.canvas
        canvas.grab()
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        before = constraint.offset
        start = canvas.to_screen(Point(3, 5)).toPoint()  # on the dimension line
        QTest.mousePress(canvas, Qt.LeftButton, Qt.NoModifier, start)
        self.assertEqual(session.selected_constraint, constraint.constraint_id)
        session.drag(Point(3, 9), TOL)  # what a mouse move with the button held does
        QTest.mouseRelease(canvas, Qt.LeftButton, Qt.NoModifier, start)
        after = session.sketch.constraints[constraint.constraint_id].offset
        self.assertAlmostEqual(after[1], before[1] + 4)
        self.assertAlmostEqual(after[0], before[0])
        del app


if __name__ == "__main__":
    unittest.main()
