import unittest

from wop.core.geometry import Point
from wop.core.sketch.loops import find_chains
from wop.ui.sketch_constants import TOOL_CIRCLE, TOOL_DIMENSION, TOOL_LINE, TOOL_MIRROR, TOOL_SELECT, TOOL_TRIM
from wop.core.sketch.modes import TURNING
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_target import SketchTarget

TOL = 0.5


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)
    session.release(Point(x, z), TOL)


def _polyline(*points: tuple[float, float]) -> SketchSession:
    session = SketchSession()
    session.set_tool(TOOL_LINE)
    for x, z in points:
        _click(session, x, z)
    session.cancel()
    session.set_tool(TOOL_SELECT)
    return session


class ModifySessionTests(unittest.TestCase):
    def test_fillet_the_selected_corner(self):
        session = _polyline((0, 0), (0, 10), (10, 10))
        _click(session, 0, 10)  # the corner point
        self.assertTrue(session.available_modify("fillet"))
        self.assertTrue(session.apply_corner("fillet", 3))
        self.assertEqual(len(session.sketch.arcs), 1)
        self.assertEqual(len(find_chains(session.sketch)[0].pieces), 3)
        self.assertAlmostEqual(session.sketch.segment(next(iter(session.sketch.arcs.values()))).radius, 3)

    def test_chamfer_and_the_message_when_it_does_not_fit(self):
        session = _polyline((0, 0), (0, 10), (10, 10))
        _click(session, 0, 10)
        self.assertFalse(session.apply_corner("chamfer", 50))
        self.assertTrue(session.message)
        self.assertEqual(len(session.sketch.lines), 2)  # nothing changed
        self.assertTrue(session.apply_corner("chamfer", 2))
        self.assertEqual(len([l for l in session.sketch.lines.values() if not l.construction]), 3)  # the outline
        self.assertEqual(len([l for l in session.sketch.lines.values() if l.reference]), 2)  # and the sharp corner, kept

    def test_the_sharp_corner_can_be_dimensioned_after_the_fillet(self):
        session = _polyline((0, 0), (0, 10), (10, 10))
        _click(session, 0, 10)
        session.apply_corner("fillet", 3)
        corner = next(i for i, p in session.sketch.points.items() if (p.x, p.z) == (0, 10))
        session.set_tool(TOOL_DIMENSION)
        _click(session, 0, 10)  # the point of the original corner: still there to pick
        self.assertEqual(session.dim_picks, [("point", corner)])

    def test_a_reference_line_that_is_made_a_real_line_again_is_a_normal_line(self):
        session = _polyline((0, 0), (0, 10), (10, 10))
        _click(session, 0, 10)
        session.apply_corner("fillet", 3)
        old = next(l for l in session.sketch.lines.values() if l.reference)
        session.selected_points, session.selected_pieces = set(), {old.line_id}
        session.toggle_construction()
        again = session.sketch.lines[old.line_id]
        self.assertFalse(again.construction or again.reference)

    def test_corner_is_not_available_on_an_end_point(self):
        session = _polyline((0, 0), (0, 10), (10, 10))
        _click(session, 0, 0)
        self.assertFalse(session.available_modify("fillet"))

    def test_fillet_can_be_undone(self):
        session = _polyline((0, 0), (0, 10), (10, 10))
        _click(session, 0, 10)
        session.apply_corner("fillet", 3)
        session.undo()
        self.assertEqual(session.sketch.arcs, {})
        self.assertEqual(len(session.sketch.lines), 2)

    def test_construction_toggle_takes_a_line_out_of_the_outline(self):
        session = _polyline((0, 0), (0, 10))
        _click(session, 0, 5)
        self.assertTrue(session.toggle_construction())
        self.assertTrue(next(iter(session.sketch.lines.values())).construction)
        self.assertEqual(find_chains(session.sketch), [])
        session.toggle_construction()
        self.assertFalse(next(iter(session.sketch.lines.values())).construction)

    def _profile_and_axis(self, kind="normal"):
        """A profile along z at radius 10 and 20 (two lines) and, apart from it, a line along z at x = 0 as the mirror line."""
        session = _polyline((10, 0), (10, -20), (20, -20))
        session.set_tool(TOOL_LINE)
        _click(session, 0, -30)
        _click(session, 0, 10)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        axis = max(session.sketch.lines)
        if kind == "construction":
            session.selected_pieces = {axis}
            session.toggle_construction()
        elif kind == "centre":
            session.selected_pieces = {axis}
            session.toggle_centre()
        session.selected_pieces = {i for i in session.sketch.lines if i != axis}
        return session, axis

    def test_select_press_mirror_and_click_a_line(self):
        for kind in ("normal", "construction", "centre"):  # any type of line will do
            with self.subTest(kind):
                session, axis = self._profile_and_axis(kind)
                self.assertTrue(session.available_tool(TOOL_MIRROR))
                session.set_tool(TOOL_MIRROR)
                self.assertEqual(session.tool, TOOL_MIRROR)
                self.assertEqual(len(session.selected_pieces), 2)  # the selection is kept for the click on the line
                _click(session, 0, -15)
                self.assertEqual(len(session.sketch.lines), 5)  # the axis, the profile and its two copies
                self.assertEqual(session.tool, TOOL_SELECT)  # the tool is off again
                self.assertEqual(len(session.selected_pieces), 2)  # and the copies are selected
                xs = sorted(p.x for p in session.sketch.points.values())
                self.assertIn(-10, xs)
                self.assertIn(-20, xs)

    def test_the_mirror_is_one_undo_step_and_the_copies_follow_the_original(self):
        session, axis = self._profile_and_axis()
        before = session.sketch.signature()
        session.set_tool(TOOL_MIRROR)
        _click(session, 0, -15)
        self.assertNotEqual(session.sketch.signature(), before)
        session.undo()
        self.assertEqual(session.sketch.signature(), before)

    def test_the_line_that_is_clicked_is_never_mirrored_about_itself(self):
        session, axis = self._profile_and_axis()
        session.selected_pieces = set(session.sketch.lines)  # everything is selected, the axis too
        session.set_tool(TOOL_MIRROR)
        _click(session, 0, -15)
        self.assertEqual(len(session.sketch.lines), 5)

    def test_nothing_selected_means_the_mirror_tool_does_not_start(self):
        session, axis = self._profile_and_axis()
        session.selected_pieces = set()
        self.assertFalse(session.available_tool(TOOL_MIRROR))
        session.set_tool(TOOL_MIRROR)
        self.assertEqual(session.tool, TOOL_SELECT)
        self.assertIn("Select what to mirror", session.message)

    def test_a_click_that_is_not_on_a_line_says_so_and_waits_and_escape_drops_the_selection(self):
        session, axis = self._profile_and_axis()
        session.set_tool(TOOL_MIRROR)
        _click(session, 50, 50)
        self.assertTrue(session.message)
        self.assertEqual(session.tool, TOOL_MIRROR)
        session.escape()
        self.assertEqual(session.tool, TOOL_SELECT)
        self.assertEqual(session.selected_pieces, set())  # Esc drops every selection
        self.assertEqual(len(session.sketch.lines), 3)

    def test_an_arc_is_not_a_mirror_line(self):
        session = _polyline((10, 0), (10, -20))
        session.set_tool(TOOL_CIRCLE)
        _click(session, 0, 0)
        _click(session, 0, 5)
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = set(session.sketch.lines)
        session.set_tool(TOOL_MIRROR)
        _click(session, 5, 0)  # on the circle
        self.assertEqual(session.tool, TOOL_MIRROR)
        self.assertEqual(len(session.sketch.lines), 1)

    def test_the_spindle_axis_of_a_turning_contour_is_a_mirror_line(self):
        session = SketchSession(target=SketchTarget(TURNING, "part"))
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((10, 0), (10, -20), (20, -20)):
            _click(session, x, z)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = set(session.sketch.lines)
        session.set_tool(TOOL_MIRROR)
        session.move_hover(Point(0.2, -40), TOL)
        self.assertEqual(session.hover_axis, "z")
        _click(session, 0.2, -40)
        self.assertEqual(len(session.sketch.lines), 4)
        self.assertIn(-10, [p.x for p in session.sketch.points.values()])
        free = SketchSession()
        free.set_tool(TOOL_LINE)
        self.assertIsNone(free.mirror_axis_at(Point(0.2, -40), TOL))  # a free sketch has no axis of its own

    def test_the_line_under_the_mouse_is_known_while_the_tool_is_on(self):
        session, axis = self._profile_and_axis()
        session.set_tool(TOOL_MIRROR)
        session.move_hover(Point(0, -15), TOL)
        self.assertEqual(session.hover_axis, axis)
        session.move_hover(Point(50, 50), TOL)
        self.assertIsNone(session.hover_axis)

    def test_the_copies_stay_tied_to_the_originals(self):
        session, axis = self._profile_and_axis()
        session.sketch.add_constraint("fixed", (session.sketch.lines[axis].start,), (0, -30))
        session.sketch.add_constraint("fixed", (session.sketch.lines[axis].end,), (0, 10))
        session.set_tool(TOOL_MIRROR)
        _click(session, 0, -15)
        self.assertTrue(any(c.kind == "symmetric" for c in session.sketch.constraints.values()))

    def test_trim_tool_cuts_back_to_the_crossing(self):
        session = _polyline((0, 0), (0, 20))
        session.set_tool(TOOL_LINE)
        _click(session, -5, 10)
        _click(session, 5, 10)
        session.cancel()
        session.set_tool(TOOL_TRIM)
        _click(session, 0, 15)
        first = min(session.sketch.lines)
        ends = sorted(session.sketch.point(p).z for p in (session.sketch.lines[first].start, session.sketch.lines[first].end))
        self.assertAlmostEqual(ends[1], 10)

    def test_trim_where_there_is_nothing_gives_a_message(self):
        session = _polyline((0, 0), (0, 20))
        session.set_tool(TOOL_TRIM)
        _click(session, 50, 50)
        self.assertTrue(session.message)

    def test_trim_is_one_undo_step(self):
        session = _polyline((0, 0), (0, 20))
        session.set_tool(TOOL_LINE)
        _click(session, -5, 10)
        _click(session, 5, 10)
        session.cancel()
        session.set_tool(TOOL_TRIM)
        _click(session, 0, 15)
        session.undo()
        first = min(session.sketch.lines)
        self.assertAlmostEqual(session.sketch.point(session.sketch.lines[first].end).z, 20)


if __name__ == "__main__":
    unittest.main()
