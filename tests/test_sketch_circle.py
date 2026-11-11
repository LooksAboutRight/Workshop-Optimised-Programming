"""A circle is its centre and its size: the point on its edge is a handle that is hidden and does not have to be dimensioned."""

import unittest

from wop.core.geometry import Point
from wop.core.sketch.model import Sketch
from wop.core.sketch.solver import analyse
from wop.ui.sketch_constants import TOOL_CIRCLE, TOOL_DIMENSION, TOOL_SELECT
from wop.ui.sketch_session import SketchSession

TOL = 0.5


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)
    session.release(Point(x, z), TOL)


def _circle() -> tuple[SketchSession, int, int, int]:
    session = SketchSession()
    session.snapping = False
    session.set_tool(TOOL_CIRCLE)
    _click(session, 0, 0)
    _click(session, 0, 5)  # the edge point is at x = 0, z = 5
    session.set_tool(TOOL_SELECT)
    arc = next(iter(session.sketch.arcs.values()))
    return session, arc.arc_id, arc.centre, arc.start


class HiddenEdgePointTests(unittest.TestCase):
    def test_the_edge_point_is_hidden_until_the_circle_is_selected(self):
        session, arc, centre, edge = _circle()
        self.assertEqual(session.hidden_points(), {edge})
        session.selected_pieces = {arc}
        self.assertEqual(session.hidden_points(), set())
        session.selected_pieces = set()
        session.sketch.label_point(edge, "tip")  # a named point is always shown
        self.assertEqual(session.hidden_points(), set())

    def test_a_point_that_another_piece_uses_is_not_hidden(self):
        session, arc, centre, edge = _circle()
        other = session.sketch.add_point(0, 20)
        session.sketch.add_line(edge, other)
        self.assertEqual(session.hidden_points(), set())

    def test_a_hidden_point_cannot_be_clicked_or_snapped_to(self):
        session, arc, centre, edge = _circle()
        self.assertIsNone(session.pickable_point(Point(0, 5), TOL))
        self.assertIsNone(session.snap(Point(0, 5), TOL)[1])
        _click(session, 0, 5)  # clicking there picks the circle, not the point
        self.assertEqual(session.selected_pieces, {arc})
        self.assertEqual(session.selected_points, set())

    def test_the_handle_of_a_selected_circle_resizes_it(self):
        session, arc, centre, edge = _circle()
        session.selected_pieces = {arc}
        session.press(Point(0, 5), TOL)  # the handle is there now
        self.assertEqual(session.selected_points, {edge})
        session.drag(Point(0, 8), TOL)
        session.release(Point(0, 8), TOL)
        self.assertAlmostEqual(session.sketch.segment(session.sketch.arcs[arc]).radius, 8)

    def test_dragging_the_centre_moves_the_whole_circle(self):
        session, arc, centre, edge = _circle()
        session.press(Point(0, 0), TOL)
        self.assertEqual(session.selected_points, {centre})
        session.drag(Point(3, 4), TOL)
        session.release(Point(3, 4), TOL)
        segment = session.sketch.segment(session.sketch.arcs[arc])
        self.assertAlmostEqual(segment.radius, 5)
        self.assertTrue(segment.center.is_close(Point(3, 4)))

    def test_dimension_tool_does_not_pick_the_hidden_point(self):
        session, arc, centre, edge = _circle()
        session.set_tool(TOOL_DIMENSION)
        _click(session, 0, 5)
        self.assertEqual(session.dim_picks, [("arc", arc)])


class DefinedWithoutTheEdgePointTests(unittest.TestCase):
    def test_a_circle_is_fully_defined_by_its_centre_and_its_diameter(self):
        session, arc, centre, edge = _circle()
        self.assertEqual(analyse(session.sketch).free_directions, 3)  # the centre (2) and the size (1); the turning of the handle is not counted
        session.sketch.add_constraint("fixed", (centre,), (0, 0))
        self.assertEqual(analyse(session.sketch).free_directions, 1)  # only its size is free now
        session.sketch.add_constraint("diameter", (arc,), (10,))
        analysis = analyse(session.sketch)
        self.assertTrue(analysis.fully_defined)
        self.assertIn(edge, analysis.fixed_points)  # so it is drawn as fixed, with nothing done to the handle
        self.assertFalse(analysis.dependent)

    def test_the_turning_of_the_handle_does_not_hide_a_real_repeat(self):
        session, arc, centre, edge = _circle()
        session.sketch.add_constraint("radius", (arc,), (5,))
        session.sketch.add_constraint("diameter", (arc,), (10,))
        self.assertTrue(analyse(session.sketch).dependent)

    def test_the_picture_colours_a_dimensioned_circle_as_defined(self):
        session, arc, centre, edge = _circle()
        session.sketch.add_constraint("fixed", (centre,), (0, 0))
        session.set_tool(TOOL_DIMENSION)
        _click(session, 0, 5)
        _click(session, 9, 9)
        self.assertTrue(session.analysis.fully_defined)

    def test_two_circles_are_independent(self):
        sketch = Sketch()
        for z in (0, 30):
            edge = sketch.add_point(0, z + 5)
            sketch.add_arc(sketch.add_point(0, z), edge, edge)
        self.assertEqual(analyse(sketch).free_directions, 6)


if __name__ == "__main__":
    unittest.main()
