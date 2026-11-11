import os
import sys
import unittest

from wop.core.geometry import ArcDirection, ArcSegment, Point
from wop.core.sketch.loops import find_chains
from wop.ui.sketch_constants import TOOL_ARC_CENTRE, TOOL_ARC_THREE, TOOL_CIRCLE, TOOL_DIMENSION, TOOL_LINE, TOOL_SELECT
from wop.ui.sketch_session import SketchSession

TOL = 0.5


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)
    session.release(Point(x, z), TOL)


class SketchSessionTests(unittest.TestCase):
    def test_lines_continue_and_join(self):
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (0, 10), (10, 10)):
            _click(session, x, z)
        self.assertEqual(len(session.sketch.lines), 2)
        self.assertEqual(len(session.sketch.points), 3)  # the second line starts at the end of the first
        self.assertEqual(len(find_chains(session.sketch)), 1)

    def test_closing_a_loop_snaps_to_the_start(self):
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (0, 10), (10, 10), (10, 0), (0.1, 0.1)):
            _click(session, x, z)
        self.assertEqual(len(session.sketch.points), 4)
        self.assertTrue(find_chains(session.sketch)[0].closed)

    def test_nearly_horizontal_line_is_made_exact(self):
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        _click(session, 5, 0)
        _click(session, 5.2, 20)
        ends = sorted(p.x for p in session.sketch.points.values())
        self.assertEqual(ends, [5, 5])

    def test_arc_by_centre_keeps_the_radius(self):
        session = SketchSession()
        session.set_tool(TOOL_ARC_CENTRE)
        for x, z in ((0, 0), (5, 0), (0, 9)):
            _click(session, x, z)
        arc = next(iter(session.sketch.arcs.values()))
        segment = session.sketch.segment(arc)
        self.assertIsInstance(segment, ArcSegment)
        self.assertAlmostEqual(segment.radius, 5)
        self.assertAlmostEqual(segment.end.z, 5)
        self.assertIs(segment.direction, ArcDirection.CCW)

    def test_arc_by_three_points_goes_through_the_third(self):
        session = SketchSession()
        session.set_tool(TOOL_ARC_THREE)
        for x, z in ((0, -5), (0, 5), (5, 0)):
            _click(session, x, z)
        segment = session.sketch.segment(next(iter(session.sketch.arcs.values())))
        self.assertAlmostEqual(segment.radius, 5)
        self.assertTrue(segment.point_at(0.5).is_close(Point(5, 0), 1e-6))

    def test_collinear_three_point_arc_gives_a_message_and_keeps_the_clicks(self):
        session = SketchSession()
        session.set_tool(TOOL_ARC_THREE)
        for x, z in ((0, 0), (0, 10), (0, 5)):
            _click(session, x, z)
        self.assertEqual(session.sketch.arcs, {})
        self.assertTrue(session.message)
        self.assertEqual(len(session.pending), 2)

    def test_undo_and_redo(self):
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        _click(session, 0, 0)
        _click(session, 0, 10)
        session.undo()
        self.assertEqual(session.sketch.lines, {})
        session.redo()
        self.assertEqual(len(session.sketch.lines), 1)

    def test_drag_moves_a_point_and_dropping_on_another_joins(self):
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        _click(session, 0, 0)
        _click(session, 0, 10)
        session.cancel()
        _click(session, 8, 0)
        _click(session, 8, 10)
        session.set_tool(TOOL_SELECT)
        session.press(Point(8, 10), TOL)
        session.drag(Point(3, 10), TOL)
        session.release(Point(0, 10), TOL)  # dropped on the end of the first line
        self.assertEqual(len(session.sketch.points), 3)

    def test_delete_selected_piece(self):
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        _click(session, 0, 0)
        _click(session, 0, 10)
        session.set_tool(TOOL_SELECT)
        session.press(Point(0, 5), TOL)  # on the line, away from both points
        session.delete_selected()
        self.assertEqual(session.sketch.lines, {})
        self.assertEqual(session.sketch.points, {})

    def test_circle_is_a_full_circle_and_a_closed_chain(self):
        session = SketchSession()
        session.set_tool(TOOL_CIRCLE)
        _click(session, 0, 0)
        _click(session, 0, 5)
        segment = session.sketch.segment(next(iter(session.sketch.arcs.values())))
        self.assertTrue(segment.is_full_circle)
        self.assertAlmostEqual(segment.radius, 5)
        chains = find_chains(session.sketch)
        self.assertTrue(chains[0].closed)

    def test_snapping_can_be_switched_off(self):
        session = SketchSession()
        session.snapping = False
        session.set_tool(TOOL_LINE)
        _click(session, 0, 0)
        _click(session, 0, 10)
        _click(session, 0.1, 10.1)  # near the end of the line, but no snap: a new, very short line
        self.assertEqual(len(session.sketch.points), 3)

    def _two_lines(self) -> SketchSession:
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (0, 10)):
            _click(session, x, z)
        session.cancel()
        for x, z in ((20, 0), (20, 10)):
            _click(session, x, z)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        return session

    def test_dragging_a_line_moves_both_ends(self):
        session = self._two_lines()
        session.press(Point(0, 5), TOL)
        session.drag(Point(3, 5), TOL)
        session.release(Point(3, 5), TOL)
        xs = sorted(p.x for p in session.sketch.points.values())
        self.assertEqual(xs, [3, 3, 20, 20])

    def test_dragging_a_circle_moves_it_whole(self):
        session = SketchSession()
        session.set_tool(TOOL_CIRCLE)
        _click(session, 0, 0)
        _click(session, 0, 5)
        session.set_tool(TOOL_SELECT)
        session.press(Point(5, 0), TOL)  # on the circle
        session.drag(Point(7, 1), TOL)
        session.release(Point(7, 1), TOL)
        segment = session.sketch.segment(next(iter(session.sketch.arcs.values())))
        self.assertAlmostEqual(segment.radius, 5)
        self.assertAlmostEqual(segment.center.x, 2)
        self.assertAlmostEqual(segment.center.z, 1)

    def test_box_selects_what_is_inside_and_shift_adds(self):
        session = self._two_lines()
        session.press(Point(-2, -2), TOL)  # empty space: starts a box
        session.drag(Point(12, 12), TOL)
        session.release(Point(12, 12), TOL)
        self.assertEqual(len(session.selected_pieces), 1)
        self.assertEqual(len(session.selected_points), 2)
        session.press(Point(20, 5), TOL, add=True)  # shift-click the other line
        session.release(Point(20, 5), TOL, add=True)
        self.assertEqual(len(session.selected_pieces), 2)

    def test_delete_removes_the_pieces_of_a_selected_point(self):
        session = self._two_lines()
        session.press(Point(0, 0), TOL)
        session.release(Point(0, 0), TOL)
        session.delete_selected()
        self.assertEqual(len(session.sketch.lines), 1)

    def test_click_on_empty_space_clears_the_selection(self):
        session = self._two_lines()
        session.press(Point(0, 5), TOL)
        session.release(Point(0, 5), TOL)
        session.press(Point(50, 50), TOL)
        session.release(Point(50, 50), TOL)
        self.assertEqual(session.selected_pieces, set())

    def test_right_click_ends_the_line_but_escape_also_goes_back_to_selecting(self):
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        _click(session, 0, 0)
        session.cancel()  # right click
        self.assertEqual((session.tool, session.pending), (TOOL_LINE, []))
        _click(session, 0, 0)
        session.escape()
        self.assertEqual((session.tool, session.pending), (TOOL_SELECT, []))

    def test_preview_follows_the_mouse(self):
        session = SketchSession()
        session.set_tool(TOOL_LINE)
        _click(session, 0, 0)
        session.move_hover(Point(3, 4), TOL)
        self.assertEqual(len(session.preview_segments()), 1)


HAVE_REAL_QT = False
try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    pass


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class SketchDialogTests(unittest.TestCase):
    def test_window_opens_draws_and_paints(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        from wop.ui.qt.sketch_dialog import SketchDialog

        app = QApplication.instance() or QApplication([])
        dialog = SketchDialog()
        dialog.show()
        dialog.session.set_tool(TOOL_LINE)
        canvas = dialog.canvas
        for z, x in ((50, 50), (50, 200), (300, 200)):
            QTest.mouseMove(canvas, QPointF(z, x).toPoint())
            QTest.mouseClick(canvas, Qt.LeftButton, Qt.NoModifier, QPointF(z, x).toPoint())
        self.assertEqual(len(dialog.session.sketch.lines), 2)
        dialog.grab()  # paints without an error
        self._tools_and_escape(dialog)
        self._relations_and_dimensions(dialog)
        dialog.close()
        del app

    def _tools_and_escape(self, dialog) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        self.assertNotIn(TOOL_SELECT, dialog.tool_buttons)  # selecting is what you get when no tool is on
        session = dialog.session
        session.set_tool(TOOL_SELECT)
        dialog.tool_buttons[TOOL_LINE].click()
        self.assertEqual(session.tool, TOOL_LINE)
        self.assertTrue(dialog.tool_buttons[TOOL_LINE].isChecked())
        dialog.tool_buttons[TOOL_LINE].click()  # the button of the tool that is on turns it off
        self.assertEqual(session.tool, TOOL_SELECT)
        self.assertFalse(dialog.tool_buttons[TOOL_LINE].isChecked())
        dialog.tool_buttons[TOOL_LINE].click()
        QTest.keyClick(dialog.canvas, Qt.Key_Escape)
        self.assertEqual(session.tool, TOOL_SELECT)
        self.assertFalse(any(b.isChecked() for b in dialog.tool_buttons.values()))
        # a tool turned on and not used, then Esc: the window stays open, wherever the keyboard is
        for widget in (dialog, dialog.canvas, dialog.tool_buttons[TOOL_LINE], dialog.panel.remove_button):
            dialog.tool_buttons[TOOL_LINE].click()
            QTest.keyClick(widget, Qt.Key_Escape)
            self.assertTrue(dialog.isVisible())
            self.assertEqual(session.tool, TOOL_SELECT)
        QTest.keyClick(dialog, Qt.Key_Return)  # Enter does nothing either
        self.assertTrue(dialog.isVisible())
        for button in dialog.tool_buttons.values():
            self.assertEqual(button.focusPolicy(), Qt.NoFocus)

    def _dimension_by_mouse(self, dialog) -> None:
        """Dimension the first line with the real tool: click it, move next to it and click there."""
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest

        canvas, session = dialog.canvas, dialog.session
        line = session.sketch.lines[next(iter(session.sketch.lines))]
        a, b = (canvas.to_screen(session.sketch.point(p).position) for p in (line.start, line.end))
        middle = (a + b) / 2
        if session.tool != TOOL_DIMENSION:
            dialog.tool_buttons[TOOL_DIMENSION].click()
        QTest.mouseMove(canvas, middle.toPoint())
        QTest.mouseClick(canvas, Qt.LeftButton, Qt.NoModifier, middle.toPoint())
        self.assertEqual(session.dim_picks[0][0], "line")
        beside = middle + QPointF(6, 0)  # right next to the line: its length
        QTest.mouseMove(canvas, beside.toPoint())
        session.move_hover(canvas.to_world(beside), canvas.tolerance)  # what the canvas does on a move (a simulated move is not always delivered)
        self.assertEqual(session.dimension_draft().kind, "length")
        dialog.grab()  # paints the dimension that follows the mouse
        QTest.mouseClick(canvas, Qt.LeftButton, Qt.NoModifier, beside.toPoint())
        self.assertEqual(session.dim_picks, [])

    def _click_a_tag(self, dialog) -> None:
        from unittest import mock

        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        session = dialog.session
        session.set_tool(TOOL_SELECT)
        self._dimension_by_mouse(dialog)
        session.set_tool(TOOL_SELECT)
        session.select_constraint(None)
        dialog.grab()  # draws the tags, so the canvas knows where they are
        length_id = next(i for i, c in session.sketch.constraints.items() if c.kind == "length")
        rect = next(r for r, cid in dialog.canvas._tag_rects if cid == length_id)
        QTest.mouseClick(dialog.canvas, Qt.LeftButton, Qt.NoModifier, rect.center().toPoint())
        self.assertEqual(session.selected_constraint, length_id)
        with mock.patch("wop.ui.qt.sketch_panel.ask_value", return_value=33.0):
            QTest.mouseDClick(dialog.canvas, Qt.LeftButton, Qt.NoModifier, rect.center().toPoint())
        self.assertAlmostEqual(session.sketch.constraints[length_id].values[0], 33.0)

    def _relations_and_dimensions(self, dialog) -> None:
        from unittest import mock

        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest

        session = dialog.session
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = {next(iter(session.sketch.lines))}
        session._notify()  # the buttons find out what the selection allows
        self.assertTrue(session.available_relation("horizontal"))
        self.assertFalse(session.available_relation("parallel"))
        dialog._relation("horizontal")
        session.selected_pieces = set()
        self._dimension_by_mouse(dialog)
        self.assertEqual(len(session.sketch.constraints), 2)
        self.assertEqual(dialog.panel.list.count(), 2)
        dialog.panel.list.setCurrentRow(1)  # selecting in the list marks the relation in the picture
        self.assertIsNotNone(session.selected_constraint)
        with mock.patch("wop.ui.qt.sketch_panel.ask_value", return_value=30.0):
            dialog.panel.edit_constraint(dialog.panel.list.item(1).data(256))
        dialog.panel._remove()
        self.assertEqual(len(session.sketch.constraints), 1)
        self._click_a_tag(dialog)
        dialog.tool_buttons[TOOL_DIMENSION].click()
        self.assertEqual(session.selected_pieces, set())  # turning the tool on deselects
        QTest.mouseClick(dialog.canvas, Qt.LeftButton, Qt.NoModifier, QPointF(5, 5).toPoint())  # nothing there: a message
        self.assertTrue(session.message)
        dialog.grab()


if __name__ == "__main__":
    unittest.main()
