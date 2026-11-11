"""A point or a line and a centre line (the spindle axis too): the mouse between them or beyond the thing gives the radius, the
mouse across the centre line the diameter (N42). The radius is the relation "distance to a line", the same for every centre line."""

import unittest

from wop.core.geometry import Point
from wop.core.sketch.constants import AXIS_LINE
from wop.core.sketch.modes import TURNING
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.core.sketch.solver import solve
from wop.ui.sketch_constants import AXIS_ID, TOOL_DIMENSION, TOOL_LINE, TOOL_SELECT
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_target import SketchTarget

TOL = 0.5


def _turning(x_scale: float = 1) -> SketchSession:
    """A step from radius 10 down to radius 15: a line along z at radius 10, one up, one along z at radius 15."""
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


def _pick_point_and_axis(session: SketchSession) -> None:
    _click(session, 10, 0)  # the point at radius 10
    _click(session, 0.2, -30)  # the spindle axis, away from the contour
    assert session.dimension_ready()


def _own_centre_line(session: SketchSession) -> int:
    """A centre line the user drew: slanted, from (0, -30) to (4, -60), far from the contour."""
    session.set_tool(TOOL_LINE)
    session.press(Point(0, -30), TOL)
    session.press(Point(4, -60), TOL)
    session.cancel()
    line = max(session.sketch.lines)
    session.sketch.update_piece(line, centre_line=True, construction=True)
    session.set_tool(TOOL_DIMENSION)
    return line


class RadiusFromTheMouseTests(unittest.TestCase):
    def test_between_the_point_and_the_axis_is_a_radius(self):
        session = _turning()
        _pick_point_and_axis(session)
        session.move_hover(Point(5, 15), TOL)
        draft = session.dimension_draft()
        self.assertEqual((draft.kind, draft.text), ("distance_line", "10"))
        _click(session, 5, 15)
        (constraint,) = session.sketch.constraints.values()
        self.assertEqual(constraint.kind, "distance_line")
        self.assertEqual(constraint.refs[1], AXIS_LINE)
        self.assertAlmostEqual(constraint.values[0], 10)
        self.assertEqual(session.sketch.helpers, set())  # no mirror point for a radius

    def test_beyond_the_point_on_the_same_side_is_still_a_radius(self):
        session = _turning()
        _pick_point_and_axis(session)
        session.move_hover(Point(18, 15), TOL)
        self.assertEqual(session.dimension_draft().kind, "distance_line")

    def test_across_the_axis_is_the_diameter_as_before(self):
        session = _turning()
        _pick_point_and_axis(session)
        session.move_hover(Point(-5, 15), TOL)
        draft = session.dimension_draft()
        self.assertEqual((draft.kind, draft.text), ("distance_x", "20"))
        _click(session, -5, 15)
        self.assertEqual(len(session.sketch.helpers), 1)

    def test_the_mouse_crossing_the_axis_switches_the_draft(self):
        session = _turning()
        _pick_point_and_axis(session)
        kinds = []
        for x in (14, 6, 1, -1, -6):
            session.move_hover(Point(x, 15), TOL)
            kinds.append(session.dimension_draft().kind)
        self.assertEqual(kinds, ["distance_line"] * 3 + ["distance_x"] * 2)

    def test_the_drawing_is_anchored_at_the_thing_and_at_the_axis(self):
        session = _turning()
        _pick_point_and_axis(session)
        session.move_hover(Point(5, 15), TOL)
        drawing = session.dimension_draft().drawing
        first, second, main = drawing.lines
        self.assertEqual((first[0].x, first[0].z), (10, 0))  # the extension line starts at the point
        self.assertEqual((second[0].x, second[0].z), (0, 0))  # and the other at the foot on the axis
        self.assertEqual((main[0].x, main[0].z, main[1].x, main[1].z), (10, 15, 0, 15))  # the dimension line is square to the axis
        self.assertEqual(len(drawing.arrows), 2)

    def test_the_number_of_a_radius_is_not_doubled_in_a_diameter_project(self):
        session = _turning(x_scale=2)
        _pick_point_and_axis(session)
        session.move_hover(Point(5, 15), TOL)
        self.assertEqual(session.dimension_draft().text, "10")
        _click(session, 5, 15)
        (constraint,) = session.sketch.constraints.values()
        self.assertAlmostEqual(session.display_value(constraint), 10)
        self.assertTrue(session.edit_dimension(constraint.constraint_id, 12))
        self.assertAlmostEqual(session.sketch.point(min(session.sketch.points)).x, 12)

    def test_the_value_can_be_changed_and_the_point_follows(self):
        session = _turning()
        _pick_point_and_axis(session)
        _click(session, 5, 15)
        (constraint,) = session.sketch.constraints.values()
        self.assertTrue(session.edit_dimension(constraint.constraint_id, 14))
        self.assertAlmostEqual(session.sketch.point(min(session.sketch.points)).x, 14)

    def test_a_line_along_the_axis_gives_its_radius(self):
        session = _turning()
        _click(session, 10, -10)
        _click(session, 0.2, -30)
        _click(session, 5, 15)
        (constraint,) = session.sketch.constraints.values()
        self.assertEqual(constraint.kind, "distance_line")
        self.assertAlmostEqual(constraint.values[0], 10)

    def test_the_origin_is_on_the_axis(self):
        session = _turning()
        _click(session, 0, 0)
        _click(session, 0.2, -30)
        session.move_hover(Point(5, 15), TOL)
        self.assertIsNone(session.dimension_draft())  # no radius to make
        _click(session, 5, 15)
        self.assertEqual(session.sketch.constraints, {})
        self.assertIn("origin", session.message)

    def test_a_radius_of_zero_is_refused(self):
        session = _turning()
        _click(session, 10, 0)
        _click(session, 0.2, -30)
        _click(session, 5, 15)
        (constraint,) = session.sketch.constraints.values()
        self.assertFalse(session.edit_dimension(constraint.constraint_id, 0))

    def test_the_dimension_line_slides_along_the_axis_when_it_is_dragged(self):
        session = _turning()
        _pick_point_and_axis(session)
        _click(session, 5, 15)
        (constraint,) = session.sketch.constraints.values()
        moved = session._allowed_move(constraint, (3.0, 7.0))
        self.assertEqual(moved, (0.0, 7.0))  # along z only: the axis runs along z

    def test_it_is_saved_and_loaded_with_the_axis_as_its_line(self):
        session = _turning()
        _pick_point_and_axis(session)
        _click(session, 5, 15)
        again = sketch_from_dict(sketch_to_dict(session.sketch))
        (constraint,) = again.constraints.values()
        self.assertEqual((constraint.kind, constraint.refs[1]), ("distance_line", AXIS_LINE))
        result = solve(again)
        self.assertTrue(result.converged)

    def test_choosing_the_dimension_does_not_fail_on_the_axis(self):
        session = _turning()
        _pick_point_and_axis(session)
        _click(session, 5, 15)
        (constraint,) = session.sketch.constraints.values()
        session.set_tool(TOOL_SELECT)
        session.selected_constraint = constraint.constraint_id
        points, pieces = session.constraint_members()
        self.assertEqual((len(points), pieces), (1, set()))


class RadiusToADrawnCentreLineTests(unittest.TestCase):
    def test_the_distance_is_square_to_the_line(self):
        session = _turning()
        line = _own_centre_line(session)
        _click(session, 15, -20)  # the point at radius 15
        _click(session, 2, -45)  # the centre line
        self.assertEqual(session.dim_picks[1], ("centre", line))
        point = session.dim_picks[0][1]
        start, end = (session.sketch.point(i).position for i in session._line_ends(line))
        along = (end.x - start.x, end.z - start.z)
        here = session.sketch.point(point).position
        side = along[0] * (here.z - start.z) - along[1] * (here.x - start.x)
        beside = Point(here.x + (5 if side > 0 else -5), here.z + 3)
        across = Point(here.x - (30 if side > 0 else -30), here.z)
        session.move_hover(across, TOL)
        self.assertIn(session.dimension_draft().kind, ("distance_x", "distance"))  # across the line: the diameter
        session.move_hover(beside, TOL)
        draft = session.dimension_draft()
        self.assertEqual(draft.kind, "distance_line")
        expected = abs(along[0] * (here.z - start.z) - along[1] * (here.x - start.x)) / (along[0] ** 2 + along[1] ** 2) ** 0.5
        self.assertAlmostEqual(draft.values[0], expected)

    def test_the_dimension_follows_when_the_centre_line_moves(self):
        session = _turning()
        line = _own_centre_line(session)
        start_id, end_id = session._line_ends(line)
        for point_id in (start_id, end_id):
            session.sketch.add_constraint("fixed", (point_id,), (session.sketch.point(point_id).x, session.sketch.point(point_id).z))
        _click(session, 15, -20)
        _click(session, 2, -45)
        point = session.dim_picks[0][1]
        start = session.sketch.point(start_id).position
        end = session.sketch.point(end_id).position
        along = (end.x - start.x, end.z - start.z)
        here = session.sketch.point(point).position
        side = along[0] * (here.z - start.z) - along[1] * (here.x - start.x)
        _click(session, here.x + (3 if side > 0 else -3), here.z - 5)
        (constraint,) = [c for c in session.sketch.constraints.values() if c.kind == "distance_line"]
        self.assertTrue(session.edit_dimension(constraint.constraint_id, 7))
        self.assertTrue(solve(session.sketch).converged)
        args = session.sketch.constraint_args(constraint)
        from wop.core.sketch.relations import relation_for

        self.assertAlmostEqual(relation_for("distance_line").measure(args)[0], 7, places=5)

    def test_the_dimension_goes_with_its_centre_line(self):
        session = _turning()
        line = _own_centre_line(session)
        _click(session, 15, -20)
        _click(session, 2, -45)
        point = session.dim_picks[0][1]
        start = session.sketch.point(session._line_ends(line)[0]).position
        end = session.sketch.point(session._line_ends(line)[1]).position
        here = session.sketch.point(point).position
        side = (end.x - start.x) * (here.z - start.z) - (end.z - start.z) * (here.x - start.x)
        _click(session, here.x + (3 if side > 0 else -3), here.z - 5)
        self.assertTrue(any(c.kind == "distance_line" for c in session.sketch.constraints.values()))
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = {line}
        session.delete_selected()
        self.assertFalse(any(c.kind == "distance_line" for c in session.sketch.constraints.values()))


class DeleteEverythingTests(unittest.TestCase):
    def test_a_box_over_everything_and_delete_works_with_a_diameter(self):
        session = _turning()
        _pick_point_and_axis(session)
        _click(session, -5, 15)  # a diameter: it makes a hidden mirror point
        self.assertTrue(session.sketch.helpers)
        session.set_tool(TOOL_SELECT)
        session._select_in_box(Point(-50, -50), Point(50, 50), False)
        self.assertFalse(session.selected_points & session.sketch.helpers)  # the hidden points are not boxed
        session.delete_selected()  # no error
        self.assertEqual((session.sketch.lines, session.sketch.helpers), ({}, set()))

    def test_deleting_a_selected_point_that_goes_with_its_pieces_is_not_an_error(self):
        session = _turning()
        _pick_point_and_axis(session)
        _click(session, -5, 15)
        (helper,) = session.sketch.helpers
        session.set_tool(TOOL_SELECT)
        session.selected_points = {helper}  # as if it had been selected by a box in an older version
        session.selected_pieces = set(session.sketch.lines)
        session.delete_selected()
        self.assertEqual(session.sketch.lines, {})


if __name__ == "__main__":
    unittest.main()
