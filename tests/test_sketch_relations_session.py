import math
import unittest

from wop.core.geometry import Point
from wop.core.sketch.constants import ORIGIN
from wop.ui.sketch_constants import TOOL_CIRCLE, TOOL_LINE, TOOL_SELECT
from wop.ui.sketch_session import SketchSession

TOL = 0.5


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)
    session.release(Point(x, z), TOL)


def _line(x1: float, z1: float, x2: float, z2: float) -> SketchSession:
    session = SketchSession()
    session.snapping = False
    session.set_tool(TOOL_LINE)
    _click(session, x1, z1)
    _click(session, x2, z2)
    session.cancel()
    session.set_tool(TOOL_SELECT)
    return session


def _select_line(session: SketchSession) -> None:
    mid = next(iter(session.sketch.lines.values()))
    a, b = session.sketch.point(mid.start), session.sketch.point(mid.end)
    _click(session, (a.x + b.x) / 2, (a.z + b.z) / 2)


class RelationSessionTests(unittest.TestCase):
    def test_horizontal_makes_the_selected_line_level(self):
        session = _line(0, 0, 3, 10)
        _select_line(session)
        self.assertTrue(session.available_relation("horizontal"))
        self.assertTrue(session.apply_relation("horizontal"))
        a, b = session.sketch.points.values()
        self.assertAlmostEqual(a.x, b.x)

    def test_horizontal_turns_a_steep_line_and_keeps_its_length(self):
        session = _line(0, 0, 8, 0)  # exactly vertical in the picture
        _select_line(session)
        self.assertTrue(session.apply_relation("horizontal"))
        a, b = session.sketch.points.values()
        self.assertAlmostEqual(a.x, b.x)
        self.assertAlmostEqual(abs(a.z - b.z), 8)

    def test_vertical_turns_a_flat_line_and_keeps_its_length(self):
        session = _line(0, 0, 0, 8)
        _select_line(session)
        self.assertTrue(session.apply_relation("vertical"))
        a, b = session.sketch.points.values()
        self.assertAlmostEqual(a.z, b.z)
        self.assertAlmostEqual(abs(a.x - b.x), 8)

    def test_relation_that_does_not_fit_the_selection_is_refused(self):
        session = _line(0, 0, 3, 10)
        _select_line(session)
        self.assertFalse(session.available_relation("parallel"))
        self.assertFalse(session.apply_relation("parallel"))
        self.assertTrue(session.message)

    def test_length_dimension_shows_the_measured_value_and_drives_the_line(self):
        session = _line(0, 0, 0, 10)
        _select_line(session)
        plan = session.plan_dimension("length")
        self.assertAlmostEqual(plan.shown, 10)
        self.assertTrue(session.add_dimension(plan, 25))
        a, b = session.sketch.points.values()
        self.assertAlmostEqual(math.hypot(a.x - b.x, a.z - b.z), 25)

    def test_conflicting_dimension_is_refused_and_nothing_changes(self):
        session = _line(0, 0, 0, 10)
        _select_line(session)
        session.add_dimension(session.plan_dimension("length"), 12)
        before = session.sketch.signature()
        self.assertFalse(session.add_dimension(session.plan_dimension("along_z"), 5))  # z length 12 is fixed by the length
        self.assertEqual(session.sketch.signature(), before)
        self.assertIn("does not fit", session.message)

    def test_zero_length_is_refused(self):
        session = _line(0, 0, 0, 10)
        _select_line(session)
        self.assertFalse(session.add_dimension(session.plan_dimension("length"), 0))

    def test_undo_takes_a_relation_back(self):
        session = _line(0, 0, 3, 10)
        _select_line(session)
        session.apply_relation("horizontal")
        session.undo()
        self.assertEqual(session.sketch.constraints, {})
        a, b = session.sketch.points.values()
        self.assertNotAlmostEqual(a.x, b.x)

    def test_fixed_and_the_analysis(self):
        session = _line(0, 0, 0, 10)
        self.assertEqual(session.analysis.free_directions, 4)
        _select_line(session)
        session.apply_relation("fixed")
        self.assertTrue(session.analysis.fully_defined)  # both points are pinned

    def test_a_point_and_the_origin(self):
        session = _line(2, 3, 2, 9)
        a = min(session.sketch.points)
        session.selected_points = {a}
        plan = session.plan_dimension("along_z")
        self.assertEqual(plan.refs, (ORIGIN, a))
        self.assertAlmostEqual(plan.shown, 3)
        self.assertTrue(session.add_dimension(plan, 4))
        self.assertAlmostEqual(session.sketch.point(a).z, 4)

    def test_dragging_keeps_a_horizontal_line_horizontal(self):
        session = _line(0, 0, 0, 10)
        _select_line(session)
        session.apply_relation("horizontal")
        session.selected_points, session.selected_pieces = set(), set()
        end = max(session.sketch.points)
        session.press(Point(0, 10), TOL)
        session.drag(Point(6, 14), TOL)
        session.release(Point(6, 14), TOL)
        a, b = session.sketch.points.values()
        self.assertAlmostEqual(a.x, b.x, places=6)
        self.assertGreater(session.sketch.point(end).z, 12)  # it followed the mouse along z

    def test_dragging_a_fully_defined_line_does_not_move_it(self):
        session = _line(0, 0, 0, 10)
        _select_line(session)
        session.apply_relation("fixed")
        session.selected_points, session.selected_pieces = set(), set()
        session.press(Point(0, 10), TOL)
        session.drag(Point(5, 15), TOL)
        session.release(Point(5, 15), TOL)
        self.assertAlmostEqual(session.sketch.point(max(session.sketch.points)).z, 10, places=5)

    def test_drag_is_one_undo_step(self):
        session = _line(0, 0, 0, 10)
        session.press(Point(0, 10), TOL)
        for z in (11, 12, 13):
            session.drag(Point(0, z), TOL)
        session.release(Point(0, 13), TOL)
        session.undo()
        self.assertAlmostEqual(session.sketch.point(max(session.sketch.points)).z, 10)

    def test_click_without_moving_leaves_no_undo_entry(self):
        session = _line(0, 0, 0, 10)
        session.undo()  # the line itself
        session = _line(0, 0, 0, 10)
        steps = len(session._undo)
        _click(session, 0, 10)
        self.assertEqual(len(session._undo), steps)

    def test_join_two_points(self):
        session = SketchSession()
        session.snapping = False
        session.set_tool(TOOL_LINE)
        _click(session, 0, 0)
        _click(session, 0, 10)
        session.cancel()
        _click(session, 0, 10.4)
        _click(session, 5, 20)
        session.cancel()
        a, b = sorted(session.sketch.points)[1], sorted(session.sketch.points)[2]
        session.selected_points = {a, b}
        self.assertTrue(session.available_relation("join"))
        self.assertTrue(session.apply_relation("join"))
        self.assertEqual(len(session.sketch.points), 3)

    def test_circle_radius_and_diameter(self):
        session = SketchSession()
        session.snapping = False
        session.set_tool(TOOL_CIRCLE)
        _click(session, 0, 0)
        _click(session, 0, 5)
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = set(session.sketch.arcs)
        plan = session.plan_dimension("diameter")
        self.assertAlmostEqual(plan.shown, 10)
        self.assertTrue(session.add_dimension(plan, 16))
        self.assertAlmostEqual(session.sketch.segment(next(iter(session.sketch.arcs.values()))).radius, 8)

    def test_edit_and_remove_a_dimension(self):
        session = _line(0, 0, 0, 10)
        _select_line(session)
        session.add_dimension(session.plan_dimension("length"), 12)
        (constraint_id,) = session.sketch.constraints
        self.assertTrue(session.edit_dimension(constraint_id, 20))
        a, b = session.sketch.points.values()
        self.assertAlmostEqual(math.hypot(a.x - b.x, a.z - b.z), 20)
        session.remove_constraint(constraint_id)
        self.assertEqual(session.sketch.constraints, {})


if __name__ == "__main__":
    unittest.main()
