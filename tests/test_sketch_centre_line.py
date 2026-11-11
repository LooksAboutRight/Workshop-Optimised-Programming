"""Centre lines: a dimension to one is a diameter, made with a hidden mirror point; the spindle axis is one in a turning contour."""

import json
import unittest

from wop.core.geometry import Point
from wop.core.sketch.mirror import AXIS_Z, find_mirror_helper, mirror_helper
from wop.core.sketch.model import Sketch
from wop.core.sketch.modes import FREE, TURNING, contour_from_sketch, problems
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.core.sketch.solver import solve
from wop.core.sketch.constants import AXIS_LINE
from wop.ui.sketch_constants import AXIS_ID, TOOL_DIMENSION, TOOL_LINE, TOOL_SELECT
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_target import SketchTarget

TOL = 0.5  # the snap distance, so "close to the line" is 2.5 mm


def _turning(x_scale: float = 1) -> SketchSession:
    """A turning contour sketch: a step from radius 10 down to radius 15 (a line along z, one up, one along z)."""
    session = SketchSession(target=SketchTarget(TURNING, "t", x_scale=x_scale))
    session.snapping = False
    session.set_tool(TOOL_LINE)
    for x, z in ((10, 0), (10, -20), (15, -20), (15, -40)):
        session.press(Point(x, z), TOL)
    session.cancel()
    session.set_tool(TOOL_DIMENSION)
    return session


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)


def _helper_points(session: SketchSession) -> set[int]:
    return set(session.sketch.helpers)


class MirrorHelperTests(unittest.TestCase):
    def test_a_mirror_point_is_made_once_hidden_and_tied_by_a_symmetric_relation(self):
        sketch = Sketch()
        point = sketch.add_point(7, 3)
        helper = mirror_helper(sketch, point, AXIS_Z)
        self.assertEqual((sketch.point(helper).x, sketch.point(helper).z), (-7, 3))
        self.assertEqual(sketch.helpers, {helper})
        self.assertEqual(mirror_helper(sketch, point, AXIS_Z), helper)  # the same one again
        self.assertEqual(find_mirror_helper(sketch, point, AXIS_Z), helper)
        self.assertEqual([c.kind for c in sketch.constraints.values()], ["symmetric_axis_z"])

    def test_the_mirror_point_follows_and_a_centre_line_of_the_sketch_works_too(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 20)
        axis = sketch.add_line(a, b, centre_line=True)
        sketch.add_constraint("fixed", (a,), (0, 0))  # the centre line stays where it is
        sketch.add_constraint("fixed", (b,), (0, 20))
        point = sketch.add_point(4, 5)
        helper = mirror_helper(sketch, point, axis)
        self.assertEqual((sketch.point(helper).x, sketch.point(helper).z), (-4, 5))
        solve(sketch, {point: Point(6, 5)})  # a drag pulls the point; the relations are then made exact
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(helper).x, -sketch.point(point).x, places=6)
        self.assertGreater(sketch.point(point).x, 5)  # and the point did follow the pull

    def test_it_stays_only_while_a_dimension_uses_it(self):
        sketch = Sketch()
        point = sketch.add_point(5, 0)
        sketch.add_line(point, sketch.add_point(5, 10))
        helper = mirror_helper(sketch, point, AXIS_Z)
        sketch.drop_unused_points()
        self.assertNotIn(helper, sketch.points)  # nothing but its own relation uses it: gone, and the relation with it
        self.assertEqual(sketch.constraints, {})
        helper = mirror_helper(sketch, point, AXIS_Z)
        dimension = sketch.add_constraint("distance", (point, helper), (10,))
        sketch.drop_unused_points()
        self.assertIn(helper, sketch.points)
        sketch.remove_constraint(dimension)
        self.assertNotIn(helper, sketch.points)
        self.assertEqual(sketch.helpers, set())

    def test_it_goes_when_the_point_it_mirrors_goes(self):
        sketch = Sketch()
        a, b = sketch.add_point(5, 0), sketch.add_point(5, 10)
        line = sketch.add_line(a, b)
        helper = mirror_helper(sketch, a, AXIS_Z)
        sketch.add_constraint("distance", (a, helper), (10,))
        sketch.delete_piece(line)
        self.assertEqual((sketch.points, sketch.helpers, sketch.constraints), ({}, set(), {}))

    def test_helpers_and_centre_lines_are_saved(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 9)
        sketch.add_line(a, b, centre_line=True)
        point = sketch.add_point(3, 3)
        helper = mirror_helper(sketch, point, AXIS_Z)
        sketch.add_constraint("distance", (point, helper), (6,))
        again = sketch_from_dict(json.loads(json.dumps(sketch_to_dict(sketch))))
        self.assertEqual(again.signature(), sketch.signature())
        self.assertTrue(next(iter(again.lines.values())).centre_line)
        self.assertEqual(again.helpers, {helper})

    def test_a_centre_line_is_a_construction_line_and_not_part_of_the_outline(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 9)
        line = sketch.add_line(a, b, centre_line=True)
        self.assertTrue(sketch.lines[line].construction)
        self.assertEqual(problems(sketch, FREE), [])
        self.assertIn("Draw the outline", problems(sketch, TURNING)[0])


class DiameterDimensionTests(unittest.TestCase):
    def test_a_point_and_the_spindle_axis_give_the_diameter(self):
        session = _turning()
        _click(session, 10, 0)  # the point at radius 10
        _click(session, 0.2, -30)  # the spindle axis: close to x = 0, away from the contour
        self.assertEqual(session.dim_picks[1], ("centre", AXIS_ID))
        self.assertTrue(session.dimension_ready())
        session.move_hover(Point(-5, 15), TOL)  # across the axis, between the point and its mirror point: the diameter
        draft = session.dimension_draft()
        self.assertEqual((draft.kind, draft.text), ("distance_x", "20"))
        _click(session, -5, 15)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        self.assertAlmostEqual(constraint.values[0], 20)
        (helper,) = session.sketch.helpers
        self.assertEqual(set(constraint.refs), {min(session.sketch.points), helper})
        self.assertAlmostEqual(session.sketch.point(helper).x, -10)

    def test_the_mirror_point_is_not_shown_and_cannot_be_clicked(self):
        session = _turning()
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        _click(session, -5, 15)
        (helper,) = session.sketch.helpers
        self.assertIn(helper, session.hidden_points())
        self.assertIsNone(session.pickable_point(Point(-10, 0), TOL))
        session.set_tool(TOOL_SELECT)
        _click(session, -10, 0)
        self.assertEqual(session.selected_points, set())

    def test_the_drawing_goes_across_the_axis_with_an_arrow_at_each_end(self):
        session = _turning()
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        session.move_hover(Point(-5, 15), TOL)
        drawing = session.dimension_draft().drawing
        main = drawing.lines[-1]
        self.assertEqual(sorted((main[0].x, main[1].x)), [-10, 10])  # from one side of the axis to the other
        self.assertEqual(len(drawing.arrows), 2)

    def test_a_dimension_across_a_centre_line_is_called_a_diameter_in_the_list(self):
        session = _turning()
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        session.move_hover(Point(-5, 15), TOL)
        draft = session.dimension_draft()
        self.assertEqual(draft.kind, "distance_x")
        self.assertIn("Diameter", session.kind_label(draft.kind, draft.refs))  # before it is placed
        _click(session, -5, 15)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        self.assertIn("Diameter", session.kind_label(constraint.kind, constraint.refs))  # and when it is
        self.assertNotIn("radius", session.kind_label(constraint.kind, constraint.refs))
        origin_session = _turning()  # a distance from the origin is still a radius
        _click(origin_session, 0, 0)
        _click(origin_session, 10, 0)
        origin_session.move_hover(Point(-5, 15), TOL)
        draft = origin_session.dimension_draft()
        self.assertIn("radius", origin_session.kind_label(draft.kind, draft.refs))

    def test_the_number_is_the_diameter_in_a_diameter_project_too_not_doubled_again(self):
        session = _turning(x_scale=2)
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        session.move_hover(Point(-5, 15), TOL)
        self.assertEqual(session.dimension_draft().text, "20")
        _click(session, -5, 15)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        self.assertAlmostEqual(session.display_value(constraint), 20)
        self.assertTrue(session.edit_dimension(constraint.constraint_id, 24))
        self.assertAlmostEqual(session.sketch.point(min(session.sketch.points)).x, 12)

    def test_changing_the_diameter_moves_the_point_and_its_mirror_point(self):
        session = _turning()
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        _click(session, -5, 15)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        self.assertTrue(session.edit_dimension(constraint.constraint_id, 30))
        point = min(session.sketch.points)
        (helper,) = session.sketch.helpers
        self.assertAlmostEqual(session.sketch.point(point).x, 15)
        self.assertAlmostEqual(session.sketch.point(helper).x, -15)

    def test_a_line_along_the_axis_is_dimensioned_at_its_start(self):
        session = _turning()
        _click(session, 10, -10)  # the first line: it runs along z at radius 10
        _click(session, 0.2, -30)  # the spindle axis
        self.assertEqual([k for k, _ in session.dim_picks], ["line", "centre"])
        _click(session, -5, 15)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        self.assertAlmostEqual(constraint.values[0], 20)

    def test_a_sloped_line_and_the_axis_give_the_angle_to_the_axis(self):
        session = SketchSession(target=SketchTarget(TURNING, "t"))
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((10, 0), (20, -20)):
            session.press(Point(x, z), TOL)
        session.cancel()
        session.set_tool(TOOL_DIMENSION)
        _click(session, 15, -10)
        _click(session, 0.2, -30)
        session.move_hover(Point(12, -5), TOL)
        draft = session.dimension_draft()
        self.assertEqual(draft.kind, "angle")
        self.assertEqual(draft.refs[0], AXIS_LINE)  # the spindle axis is the first line of the angle, like any drawn line
        self.assertTrue(draft.drawing.curve and draft.drawing.lines)  # it is drawn: an arc with extension lines

    def test_the_axis_is_only_there_in_a_turning_contour(self):
        session = SketchSession()  # a free sketch
        session.set_tool(TOOL_DIMENSION)
        _click(session, 0.2, 5)
        self.assertEqual(session.dim_picks, [])
        self.assertTrue(session.message)

    def test_the_origin_is_not_a_point_to_dimension_across_the_axis(self):
        session = _turning()
        _click(session, 0, 0)  # the origin
        _click(session, 0.2, -30)
        session.move_hover(Point(-5, 15), TOL)
        self.assertIsNone(session.dimension_draft())  # nothing to mirror: no dimension
        _click(session, -5, 15)
        self.assertEqual(session.sketch.constraints, {})

    def test_undo_takes_the_dimension_and_the_mirror_point_back(self):
        session = _turning()
        before = session.sketch.signature()
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        _click(session, -5, 15)
        self.assertTrue(session.sketch.helpers)
        session.undo()
        self.assertEqual(session.sketch.signature(), before)

    def test_removing_the_dimension_removes_the_mirror_point(self):
        session = _turning()
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        _click(session, -5, 15)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        session.remove_constraint(constraint.constraint_id)
        self.assertEqual((session.sketch.helpers, session.sketch.constraints), (set(), {}))

    def test_the_contour_made_from_it_has_no_trace_of_the_mirror_point(self):
        session = _turning()
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        _click(session, -5, 15)
        contour = contour_from_sketch(session.sketch, TURNING, "c", "n")
        self.assertEqual(len(contour.segments), 3)
        self.assertTrue(contour.segments[0].start.is_close(Point(10, 0)))


class OwnCentreLineTests(unittest.TestCase):
    def _session_with_centre_line(self) -> SketchSession:
        session = SketchSession()
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (0, 30)):  # the future centre line
            session.press(Point(x, z), TOL)
        session.cancel()
        for x, z in ((8, 5), (8, 25)):  # a line parallel to it
            session.press(Point(x, z), TOL)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = {min(session.sketch.lines)}
        session.toggle_centre()
        session.selected_pieces = set()
        return session

    def test_make_a_centre_line_and_make_it_normal_again(self):
        session = self._session_with_centre_line()
        first = session.sketch.lines[min(session.sketch.lines)]
        self.assertTrue(first.centre_line and first.construction)
        session.selected_pieces = {first.line_id}
        self.assertTrue(session.available_modify("centre"))
        session.toggle_centre()
        again = session.sketch.lines[first.line_id]
        self.assertFalse(again.centre_line or again.construction)

    def test_a_parallel_line_and_a_centre_line_give_the_diameter(self):
        session = self._session_with_centre_line()
        session.set_tool(TOOL_DIMENSION)
        _click(session, 8, 15)  # the parallel line
        _click(session, 0, 10)  # the centre line
        self.assertEqual([k for k, _ in session.dim_picks], ["line", "centre"])
        _click(session, -4, 40)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_x"]
        self.assertAlmostEqual(constraint.values[0], 16)
        self.assertEqual(len(session.sketch.helpers), 1)

    def test_a_sloped_line_and_a_centre_line_give_an_angle_between_the_lines(self):
        session = self._session_with_centre_line()
        session.sketch.move_point(max(session.sketch.points), 14, 25)  # tilt the second line
        session.set_tool(TOOL_DIMENSION)
        _click(session, 11, 15)
        _click(session, 0, 10)
        _click(session, 3, 12)
        self.assertEqual([c.kind for c in session.sketch.constraints.values()], ["angle"])

    def test_a_dimension_to_a_centre_line_goes_when_the_centre_line_goes(self):
        session = self._session_with_centre_line()
        session.set_tool(TOOL_DIMENSION)
        _click(session, 8, 25)  # the end point of the parallel line
        _click(session, 0, 10)
        _click(session, -4, 40)
        self.assertEqual(len(session.sketch.constraints), 2)  # the symmetric relation and the dimension
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = {min(session.sketch.lines)}
        session.delete_selected()
        self.assertEqual((session.sketch.constraints, session.sketch.helpers), ({}, set()))


HAVE_REAL_QT = False
try:
    import PySide6  # noqa: F401
    import sys

    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    pass


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class WindowTests(unittest.TestCase):
    def test_the_turning_window_draws_the_axis_and_the_diameter_and_offers_centre_lines(self):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from wop.ui.qt.sketch_dialog import SketchDialog

        app = QApplication.instance() or QApplication([])
        session = _turning()
        dialog = SketchDialog(session=session)
        dialog.show()
        _click(session, 10, 0)
        _click(session, 0.2, -30)  # the axis picked: it is drawn highlighted
        dialog.grab()
        session.move_hover(Point(-5, 15), TOL)
        dialog.grab()  # the diameter that follows the mouse
        _click(session, -5, 15)
        dialog.grab()  # and placed
        self.assertIn("Centre line", dialog.modify_buttons["centre"].toolTip())
        dialog.close()
        del app


if __name__ == "__main__":
    unittest.main()
