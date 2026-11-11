"""The Dimension tool: what a click picks, what the place of the dimension decides, and what it looks like."""

import json
import math
import unittest

from wop.core.geometry import ArcDirection, Point
from wop.core.sketch.constants import ORIGIN
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.core.sketch.solver import solve
from wop.ui.sketch_constants import TOOL_CIRCLE, TOOL_DIMENSION, TOOL_LINE, TOOL_SELECT
from wop.ui.sketch_dimension_graphic import KIND_ALONG_X, KIND_ALONG_Z, KIND_LENGTH, graphic, placement_kind
from wop.ui.sketch_session import SketchSession

TOL = 0.5  # the snap distance, so "close to the line" is 5 * 0.5 = 2.5 mm


def _tool_session(*points: tuple[float, float]) -> SketchSession:
    """A session with the lines through the points drawn, and the Dimension tool on."""
    session = SketchSession()
    session.snapping = False
    session.set_tool(TOOL_LINE)
    for x, z in points:
        session.press(Point(x, z), TOL)
    session.cancel()
    session.set_tool(TOOL_DIMENSION)
    return session


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)


def _only_dimension(session: SketchSession):
    (constraint,) = session.sketch.constraints.values()
    return constraint


class PlacementKindTests(unittest.TestCase):
    P, Q = Point(0, 0), Point(10, 20)  # a slanted line (x up to 10, z up to 20)

    def test_next_to_the_line_is_the_length(self):
        self.assertEqual(placement_kind(self.P, self.Q, Point(5.5, 10), 2.5), KIND_LENGTH)

    def test_to_the_side_is_the_distance_along_x(self):
        self.assertEqual(placement_kind(self.P, self.Q, Point(5, 40), 2.5), KIND_ALONG_X)
        self.assertEqual(placement_kind(self.P, self.Q, Point(5, -15), 2.5), KIND_ALONG_X)

    def test_above_or_below_is_the_distance_along_z(self):
        self.assertEqual(placement_kind(self.P, self.Q, Point(-12, 10), 2.5), KIND_ALONG_Z)
        self.assertEqual(placement_kind(self.P, self.Q, Point(30, 10), 2.5), KIND_ALONG_Z)

    def test_inside_the_box_but_away_from_the_line_is_the_length(self):
        self.assertEqual(placement_kind(self.P, self.Q, Point(9, 2), 2.5), KIND_LENGTH)

    def test_a_diagonal_corner_beyond_both_is_the_length(self):
        self.assertEqual(placement_kind(self.P, self.Q, Point(20, 30), 2.5), KIND_LENGTH)


class ToolFlowTests(unittest.TestCase):
    def test_turning_the_tool_on_deselects(self):
        session = _tool_session((0, 0), (0, 10))
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = set(session.sketch.lines)
        session.set_tool(TOOL_DIMENSION)
        self.assertEqual((session.selected_points, session.selected_pieces), (set(), set()))

    def test_line_placed_next_to_it_is_its_length_with_no_question_asked(self):
        session = _tool_session((0, 0), (0, 10))
        _click(session, 0, 5)  # pick the line
        self.assertEqual(session.dim_picks[0][0], "line")
        self.assertTrue(session.dimension_ready())
        session.move_hover(Point(1.5, 5), TOL)
        self.assertEqual(session.dimension_draft().kind, "length")
        _click(session, 1.5, 5)  # place it
        constraint = _only_dimension(session)
        self.assertEqual(constraint.kind, "length")
        self.assertAlmostEqual(constraint.values[0], 10)
        self.assertAlmostEqual(constraint.offset[0], 1.5)  # remembered relative to the middle of the line
        self.assertEqual(session.dim_picks, [])
        self.assertEqual(session.tool, TOOL_DIMENSION)  # the tool stays on

    def test_the_place_chooses_length_x_or_z_for_a_slanted_line(self):
        for place, kind, value in (
            (Point(3.5, 11), "length", math.hypot(10, 20)),
            (Point(5, 40), "distance_x", 10),
            (Point(-12, 10), "distance_z", 20),
        ):
            with self.subTest(kind):
                session = _tool_session((0, 0), (10, 20))
                _click(session, 5, 10)
                _click(session, place.x, place.z)
                constraint = _only_dimension(session)
                self.assertEqual(constraint.kind, kind)
                self.assertAlmostEqual(constraint.values[0], value)

    def test_the_along_distances_are_positive_whichever_way_the_line_was_drawn(self):
        session = _tool_session((10, 20), (0, 0))
        _click(session, 5, 10)
        _click(session, -12, 10)
        self.assertGreater(_only_dimension(session).values[0], 0)

    def test_one_point_does_nothing_and_two_points_are_dimensioned_like_a_line(self):
        session = _tool_session((0, 0), (10, 20))
        session.sketch.add_point(30, 40)
        a, b = sorted(session.sketch.points)[0], sorted(session.sketch.points)[2]
        _click(session, 0, 0)
        self.assertFalse(session.dimension_ready())
        _click(session, 50, 50)  # one point and then nothing useful
        self.assertEqual(session.sketch.constraints, {})
        self.assertTrue(session.message)
        _click(session, 30, 40)  # the second point
        self.assertTrue(session.dimension_ready())
        _click(session, 15, 60)  # to the side of the pair
        constraint = _only_dimension(session)
        self.assertEqual((constraint.kind, constraint.refs), ("distance_x", (a, b)))
        self.assertAlmostEqual(constraint.values[0], 30)

    def test_the_origin_can_be_picked(self):
        session = _tool_session((7, 8), (7, 20))
        point = min(session.sketch.points)
        _click(session, 0, 0)  # the origin
        _click(session, 7, 8)
        self.assertEqual(session.dim_picks, [("point", ORIGIN), ("point", point)])
        _click(session, 3, 30)  # to the side: along X
        constraint = _only_dimension(session)
        self.assertEqual(constraint.kind, "distance_x")
        self.assertEqual(constraint.refs, (ORIGIN, point))
        self.assertAlmostEqual(constraint.values[0], 7)

    def test_arc_gets_a_radius_and_circle_a_diameter(self):
        session = SketchSession()
        session.snapping = False
        session.set_tool(TOOL_CIRCLE)
        _click(session, 0, 0)
        _click(session, 0, 5)
        session.set_tool(TOOL_DIMENSION)
        _click(session, 5, 0)  # on the circle
        self.assertEqual(session.dimension_draft().kind, "diameter")
        _click(session, 12, 9)
        self.assertEqual(_only_dimension(session).kind, "diameter")
        self.assertAlmostEqual(_only_dimension(session).values[0], 10)
        arc_session = SketchSession()
        centre, start, end = (arc_session.sketch.add_point(*p) for p in ((0, 0), (5, 0), (0, 5)))
        arc_session.sketch.add_arc(centre, start, end, ArcDirection.CCW)
        arc_session.set_tool(TOOL_DIMENSION)
        _click(arc_session, 3.5355, 3.5355)
        _click(arc_session, 9, 9)
        self.assertEqual(_only_dimension(arc_session).kind, "radius")

    def test_two_lines_give_an_angle(self):
        session = _tool_session((0, 0), (0, 10))
        session.set_tool(TOOL_LINE)
        _click(session, 0, 0)
        _click(session, 8, 0)
        session.cancel()
        session.set_tool(TOOL_DIMENSION)
        _click(session, 0, 5)  # first line
        _click(session, 4, 0)  # a second line instead of a place
        self.assertEqual([k for k, _ in session.dim_picks], ["line", "line"])
        _click(session, 5, 5)
        constraint = _only_dimension(session)
        self.assertEqual(constraint.kind, "angle")
        self.assertAlmostEqual(abs(math.degrees(constraint.values[0])), 90)

    def test_escape_and_right_click_drop_the_picks_but_right_click_keeps_a_normal_selection(self):
        session = _tool_session((0, 0), (0, 10))
        _click(session, 0, 5)
        session.cancel()
        self.assertEqual(session.dim_picks, [])
        self.assertEqual(session.tool, TOOL_DIMENSION)
        _click(session, 0, 5)
        session.escape()
        self.assertEqual((session.tool, session.dim_picks), (TOOL_SELECT, []))
        session.selected_pieces = set(session.sketch.lines)
        session.cancel()
        self.assertTrue(session.selected_pieces)

    def test_the_same_dimension_twice_is_refused_with_a_message(self):
        session = _tool_session((0, 0), (0, 10))
        for _ in range(2):
            _click(session, 0, 5)
            _click(session, 1, 5)
        self.assertEqual(len(session.sketch.constraints), 1)
        self.assertIn("already", session.message)

    def test_a_dimension_on_something_already_fixed_is_accepted_and_reported_as_repeating(self):
        session = _tool_session((0, 0), (0, 10))
        for point_id in session.sketch.points:
            position = session.sketch.point(point_id)
            session.sketch.add_constraint("fixed", (point_id,), (position.x, position.z))
        _click(session, 0, 5)
        _click(session, 1.5, 5)
        self.assertEqual(len(session.sketch.constraints), 3)
        self.assertTrue(session.analysis.dependent)

    def test_the_dimension_follows_the_geometry_it_measures(self):
        session = _tool_session((0, 0), (0, 10))
        _click(session, 0, 5)
        _click(session, 3, 5)
        constraint = _only_dimension(session)
        drawing, text = session.dimension_drawing(constraint)
        self.assertEqual(text, "10")
        before = drawing.text_at
        a = min(session.sketch.points)
        session.sketch.move_point(a, 0, -20)
        drawing_after, _ = session.dimension_drawing(constraint)
        self.assertNotEqual(drawing_after.text_at, before)

    def test_diameter_mode_shows_the_x_distance_as_a_diameter(self):
        from wop.core.sketch.modes import TURNING
        from wop.ui.sketch_target import SketchTarget

        session = SketchSession(target=SketchTarget(TURNING, "t", x_scale=2))
        a, b = session.sketch.add_point(5, 0), session.sketch.add_point(5, 10)
        session.sketch.add_line(a, b)
        session.set_tool(TOOL_DIMENSION)
        _click(session, 0, 0)  # the origin
        _click(session, 5, 0)  # the point at radius 5
        session.move_hover(Point(2, -10), TOL)
        draft = session.dimension_draft()
        self.assertEqual((draft.kind, draft.text), ("distance_x", "10"))
        self.assertAlmostEqual(draft.values[0], 5)  # inside the sketch it is the radius


def _crossing_lines() -> SketchSession:
    """A line along z through the origin and a 45 degree line through it, with the Dimension tool on."""
    session = SketchSession()
    session.snapping = False
    session.set_tool(TOOL_LINE)
    for x, z in ((0, -10), (0, 10)):
        session.press(Point(x, z), TOL)
    session.cancel()
    for x, z in ((-5, -5), (5, 5)):
        session.press(Point(x, z), TOL)
    session.cancel()
    session.set_tool(TOOL_DIMENSION)
    return session


class AngleBetweenLinesTests(unittest.TestCase):
    def _angle_at(self, session: SketchSession, place: Point):
        _click(session, 0, 5)  # the line along z
        _click(session, 3, 3)  # the 45 degree line (second line: the angle)
        session.move_hover(place, TOL)
        return session.dimension_draft()

    def test_the_angle_is_the_one_where_the_dimension_is_placed(self):
        for place, degrees in ((Point(3, 3.5), 45), (Point(3, 1), 135), (Point(-1, -1.7), 45), (Point(-3, 3), 135)):
            with self.subTest(place=place):
                draft = self._angle_at(_crossing_lines(), place)
                self.assertEqual(draft.kind, "angle")
                self.assertEqual(draft.text, f"{degrees}°")
                self.assertAlmostEqual(abs(math.degrees(draft.values[0])), degrees)

    def test_the_arc_lies_between_the_two_lines_and_round_the_vertex(self):
        session = _crossing_lines()
        draft = self._angle_at(session, Point(3, 1))  # the wide angle (135 degrees), 3.16 mm from the vertex
        radius = math.hypot(3, 1)
        for point in draft.drawing.curve:
            self.assertAlmostEqual(point.distance_to(Point(0, 0)), radius)
        first, last = draft.drawing.curve[0], draft.drawing.curve[-1]
        angles = sorted(math.degrees(math.atan2(p.z, p.x)) for p in (first, last))
        self.assertAlmostEqual(angles[0], -90)  # one end on the line along z
        self.assertAlmostEqual(angles[1], 45)  # the other on the 45 degree line
        middle = draft.drawing.curve[len(draft.drawing.curve) // 2]
        self.assertTrue(-90 < math.degrees(math.atan2(middle.z, middle.x)) < 45)  # and the arc in between

    def test_lines_that_stop_short_get_extension_lines_to_the_vertex_and_the_arc(self):
        session = SketchSession()
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 4), (0, 10)):  # a line along z that does not reach the vertex at the origin
            session.press(Point(x, z), TOL)
        session.cancel()
        for x, z in ((4, 4), (8, 8)):
            session.press(Point(x, z), TOL)
        session.cancel()
        session.set_tool(TOOL_DIMENSION)
        _click(session, 0, 7)
        _click(session, 6, 6)
        session.move_hover(Point(20, 15), TOL)  # far out: beyond both lines
        lines = session.dimension_draft().drawing.lines
        self.assertGreaterEqual(len(lines), 3)
        self.assertTrue(any(a.is_close(Point(0, 0)) or b.is_close(Point(0, 0)) for a, b in lines))  # out to the vertex

    def test_placing_stores_the_sector_and_changing_the_number_keeps_it(self):
        session = _crossing_lines()
        self._angle_at(session, Point(3, 1))
        _click(session, 3, 1)
        constraint = _only_dimension(session)
        self.assertEqual(len(constraint.values), 3)  # angle and the flip of each ray
        line_a = min(session.sketch.lines)
        for point_id in session.sketch.lines[line_a].start, session.sketch.lines[line_a].end:
            position = session.sketch.point(point_id)
            session.sketch.add_constraint("fixed", (point_id,), (position.x, position.z))
        self.assertTrue(session.edit_dimension(constraint.constraint_id, 100))
        self.assertAlmostEqual(session.display_value(session.sketch.constraints[constraint.constraint_id]), 100)
        from wop.core.sketch.relations import relation_for

        placed = session.sketch.constraints[constraint.constraint_id]
        measured = relation_for("angle").measure(session.sketch.constraint_args(placed), placed.values)[0]
        self.assertAlmostEqual(abs(math.degrees(measured)), 100)  # the solver turned the second line to it
        draft_text = session.dimension_drawing(session.sketch.constraints[constraint.constraint_id])[1]
        self.assertEqual(draft_text, "100°")  # always shown positive

    def test_the_angle_is_saved_with_its_sector(self):
        session = _crossing_lines()
        self._angle_at(session, Point(3, 1))
        _click(session, 3, 1)
        again = sketch_from_dict(json.loads(json.dumps(sketch_to_dict(session.sketch))))
        self.assertEqual(next(iter(again.constraints.values())).values, _only_dimension(session).values)


class SavingTests(unittest.TestCase):
    def test_where_a_dimension_was_placed_is_saved(self):
        session = _tool_session((0, 0), (0, 10))
        _click(session, 0, 5)
        _click(session, 2, 5)
        again = sketch_from_dict(json.loads(json.dumps(sketch_to_dict(session.sketch))))
        (constraint,) = again.constraints.values()
        self.assertAlmostEqual(constraint.offset[0], 2)
        self.assertTrue(solve(again).converged)


class GraphicTests(unittest.TestCase):
    def test_dimension_along_z_is_horizontal_at_the_place(self):
        drawing = graphic("distance_z", [(0, 0), (4, 10)], Point(12, 0))
        main = drawing.lines[-1]
        self.assertEqual((main[0], main[1]), (Point(12, 0), Point(12, 10)))
        self.assertEqual(drawing.lines[0], (Point(0, 0), Point(12, 0)))  # an extension line from the measured point
        self.assertEqual(len(drawing.arrows), 2)

    def test_dimension_along_x_is_vertical_at_the_place(self):
        drawing = graphic("distance_x", [(0, 0), (4, 10)], Point(0, 25))
        self.assertEqual(drawing.lines[-1], (Point(0, 25), Point(4, 25)))

    def test_aligned_dimension_is_parallel_to_the_line_at_the_distance_of_the_place(self):
        drawing = graphic("length", [((0, 0), (0, 10))], Point(3, 5))
        self.assertEqual(drawing.lines[-1], (Point(3, 0), Point(3, 10)))

    def test_radius_leader_from_the_centre_through_the_circle_to_the_place(self):
        drawing = graphic("radius", [((0, 0), (5, 0), (0, 5))], Point(0, 9))
        self.assertEqual(drawing.lines[0], (Point(0, 0), Point(0, 9)))
        self.assertEqual(drawing.arrows[0][0], Point(0, 5))  # the arrow touches the arc

    def test_angle_is_an_arc_round_the_vertex(self):
        drawing = graphic("angle", [((0, 0), (0, 10)), ((0, 0), (10, 0))], Point(6, 6))
        self.assertGreater(len(drawing.curve), 3)
        radius = math.hypot(6, 6)
        for point in drawing.curve:
            self.assertAlmostEqual(point.distance_to(Point(0, 0)), radius)

    def test_parallel_lines_have_only_the_number(self):
        drawing = graphic("angle", [((0, 0), (0, 10)), ((5, 0), (5, 10))], Point(2, 2))
        self.assertEqual((drawing.lines, drawing.curve), ((), ()))


if __name__ == "__main__":
    unittest.main()
