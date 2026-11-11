"""An angle between a line and the spindle axis works like the angle between two lines: the mouse chooses which of the angles, it is
drawn with an arc and extension lines, and the value can be changed (N45)."""

import math
import unittest

from wop.core.geometry import Point
from wop.core.sketch.constants import AXIS_LINE
from wop.core.sketch.relations import relation_for
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.ui.sketch_constants import TOOL_DIMENSION, TOOL_LINE, TOOL_SELECT
from wop.core.sketch.modes import TURNING
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_target import SketchTarget

TOL = 0.5


def _session(x_scale: float = 1) -> SketchSession:
    """A turning contour with one sloped line from (10, 0) to (20, -20); its angle to the axis is 26.565 degrees (or 153.435)."""
    session = SketchSession(target=SketchTarget(TURNING, "t", x_scale=x_scale))
    session.snapping = False
    session.set_tool(TOOL_LINE)
    for x, z in ((10, 0), (20, -20)):
        session.press(Point(x, z), TOL)
    session.cancel()
    session.set_tool(TOOL_DIMENSION)
    return session


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)


def _pick(session: SketchSession) -> None:
    _click(session, 15, -10)  # the sloped line
    _click(session, 0.2, -40)  # the spindle axis, away from the line
    assert session.dimension_ready()


def _number(text: str) -> float:
    return float(text.rstrip("°"))


class AngleToTheAxisTests(unittest.TestCase):
    def test_it_is_the_angle_between_two_lines_with_the_axis_as_one_of_them(self):
        session = _session()
        _pick(session)
        session.move_hover(Point(5, -10), TOL)
        draft = session.dimension_draft()
        self.assertEqual((draft.kind, draft.refs[0]), ("angle", AXIS_LINE))
        _click(session, 5, -10)
        (constraint,) = session.sketch.constraints.values()
        self.assertEqual(constraint.kind, "angle")
        self.assertIn(AXIS_LINE, constraint.refs)

    def test_the_mouse_chooses_between_the_acute_and_the_obtuse_angle(self):
        session = _session()
        _pick(session)
        numbers = set()
        for place in (Point(8, -5), Point(8, 5), Point(30, -30), Point(-5, -30)):
            session.move_hover(place, TOL)
            numbers.add(round(_number(session.dimension_draft().text), 3))
        self.assertEqual(numbers, {26.565, 153.435})

    def test_it_is_drawn_with_an_arc_and_an_arrow_at_each_end(self):
        session = _session()
        _pick(session)
        session.move_hover(Point(8, -10), TOL)
        drawing = session.dimension_draft().drawing
        self.assertGreater(len(drawing.curve), 4)
        self.assertEqual(len(drawing.arrows), 2)

    def test_the_value_can_be_changed_and_the_line_turns_about_the_axis_side(self):
        session = _session()
        _pick(session)
        _click(session, 8, -10)
        (constraint,) = session.sketch.constraints.values()
        self.assertTrue(session.edit_dimension(constraint.constraint_id, 45))
        line = next(iter(session.sketch.lines.values()))
        start, end = session.sketch.point(line.start).position, session.sketch.point(line.end).position
        slope = math.degrees(math.atan2(abs(end.x - start.x), abs(end.z - start.z)))
        self.assertAlmostEqual(slope, 45, places=3)  # the line now runs at 45 degrees to the axis

    def test_the_number_is_never_doubled_in_a_diameter_project(self):
        session = _session(x_scale=2)
        _pick(session)
        session.move_hover(Point(8, -10), TOL)
        self.assertIn(round(_number(session.dimension_draft().text), 3), (26.565, 153.435))

    def test_it_is_saved_and_works_after_loading(self):
        session = _session()
        _pick(session)
        _click(session, 8, -10)
        again = sketch_from_dict(sketch_to_dict(session.sketch))
        (constraint,) = again.constraints.values()
        relation = relation_for(constraint.kind)
        measured = relation.measure(again.constraint_args(constraint), constraint.values)[0]
        self.assertAlmostEqual(abs(math.degrees(measured)), 26.565, places=2) if abs(math.degrees(measured)) < 90 else self.assertAlmostEqual(abs(math.degrees(measured)), 153.435, places=2)

    def test_the_dimension_goes_when_the_line_goes(self):
        session = _session()
        _pick(session)
        _click(session, 8, -10)
        session.set_tool(TOOL_SELECT)
        session.selected_pieces = set(session.sketch.lines)
        session.delete_selected()
        self.assertEqual(session.sketch.constraints, {})

    def test_a_line_along_the_axis_still_gives_a_radius_not_an_angle(self):
        session = _session()
        session.set_tool(TOOL_LINE)
        session.press(Point(7, 0), TOL)
        session.press(Point(7, -30), TOL)
        session.cancel()
        session.set_tool(TOOL_DIMENSION)
        session.dim_picks = []
        _click(session, 7, -25)
        _click(session, 0.2, -40)
        session.move_hover(Point(4, -25), TOL)
        self.assertEqual(session.dimension_draft().kind, "distance_line")


if __name__ == "__main__":
    unittest.main()
