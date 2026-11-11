import unittest

from wop.core.constants import SAFE_POINT_KEY
from wop.core.geometry import Point
from wop.core.sketch.locked import LockedPoint
from wop.core.sketch.model import Sketch
from wop.core.sketch.modes import PATH
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_stepping import CURRENT, HIDDEN, NORMAL, OLD
from wop.ui.sketch_target import SketchTarget

SAFE = LockedPoint(SAFE_POINT_KEY, 30, 5)


def _session():
    """A path of three pieces: safe -> a (down Z), a -> b (in), b -> a (back, over the same place as the second)."""
    sketch = Sketch()
    session = SketchSession(sketch, SketchTarget(PATH, "p", locked_points=(SAFE,)))
    safe = sketch.locked_points[SAFE_POINT_KEY]
    a, b = sketch.add_point(30, -10), sketch.add_point(20, -10)
    one, two, three = sketch.add_line(safe, a), sketch.add_line(a, b), sketch.add_line(b, a)
    return session, (one, two, three), (safe, a, b)


class SteppingTests(unittest.TestCase):
    def test_stepping_shows_one_more_piece_each_time_and_selects_the_current_one(self):
        session, (one, two, three), _points = _session()
        self.assertEqual([session.piece_state(i) for i in (one, two, three)], [NORMAL] * 3)
        session.step_forward()
        self.assertEqual([session.piece_state(i) for i in (one, two, three)], [CURRENT, HIDDEN, HIDDEN])
        self.assertEqual(session.selected_pieces, {one})
        session.step_forward()
        session.step_forward()
        self.assertEqual([session.piece_state(i) for i in (one, two, three)], [OLD, OLD, CURRENT])
        self.assertEqual(session.selected_pieces, {three})
        self.assertEqual(session.step_text, "Step 3 of 3: feed line")

    def test_back_goes_to_the_first_piece_and_then_shows_everything(self):
        session, pieces, _points = _session()
        for _ in range(3):
            session.step_forward()
        session.step_back()
        self.assertEqual(session.step, 1)
        session.step_back()
        session.step_back()
        self.assertIsNone(session.step)
        self.assertEqual([session.piece_state(i) for i in pieces], [NORMAL] * 3)

    def test_at_the_end_it_says_so(self):
        session, _pieces, _points = _session()
        for _ in range(4):
            session.step_forward()
        self.assertEqual(session.step, 2)
        self.assertEqual(session.message, "That is the last piece of the path")

    def test_a_broken_chain_stops_the_stepping_and_names_the_reason(self):
        session, (one, two, three), (safe, a, b) = _session()
        far = session.sketch.add_point(5, 5)
        session.sketch.add_line(far, session.sketch.add_point(5, -5))
        for _ in range(4):
            session.step_forward()
        self.assertEqual(session.step, 2)
        self.assertIn("do not follow the path", session.message)
        self.assertIn("the path stops here", session.step_text)

    def test_the_points_of_hidden_pieces_are_hidden_but_the_locked_ones_are_not(self):
        session, _pieces, (safe, a, b) = _session()
        session.step_forward()
        hidden = session.hidden_points()
        self.assertIn(b, hidden)
        self.assertNotIn(a, hidden)
        self.assertNotIn(safe, hidden)

    def test_only_the_dimensions_of_the_current_piece_are_drawn(self):
        session, (one, two, three), (safe, a, b) = _session()
        first = session.sketch.add_constraint("distance", (safe, a), (15,))
        second = session.sketch.add_constraint("distance", (a, b), (10,))
        session.step_forward()
        self.assertTrue(session.constraint_visible(session.sketch.constraints[first]))
        self.assertFalse(session.constraint_visible(session.sketch.constraints[second]))
        session.step_forward()
        self.assertFalse(session.constraint_visible(session.sketch.constraints[first]))
        self.assertTrue(session.constraint_visible(session.sketch.constraints[second]))

    def test_where_pieces_lie_on_one_place_the_current_one_is_picked(self):
        session, (one, two, three), _points = _session()
        place = Point(25, -10)  # on the second and the third piece
        session.step_forward()
        session.step_forward()
        self.assertEqual(session.pick_piece(place, 0.1).line_id, two)
        session.step_forward()
        self.assertEqual(session.pick_piece(place, 0.1).line_id, three)
        session.step_back()
        session.step_back()
        self.assertIsNone(session.pick_piece(place, 0.1))  # the pieces there are hidden: they cannot be picked

    def test_drawing_ends_the_stepping_but_dimensioning_does_not(self):
        session, _pieces, _points = _session()
        session.step_forward()
        session.set_tool("dimension")
        self.assertEqual(session.step, 0)
        session.set_tool("select")
        session.set_tool("line")
        self.assertIsNone(session.step)

    def test_escape_leaves_the_stepping_after_it_has_dropped_a_tool(self):
        session, _pieces, _points = _session()
        session.step_forward()
        session.set_tool("dimension")
        session.escape()
        self.assertEqual((session.tool, session.step), ("select", 0))  # the first Esc drops the tool
        session.escape()
        self.assertIsNone(session.step)
        self.assertEqual(session.selected_pieces, set())
        session.escape()  # nothing to leave: nothing happens
        self.assertIsNone(session.step)

    def test_a_deleted_current_piece_leaves_the_step_inside_the_path(self):
        session, (one, two, three), _points = _session()
        for _ in range(3):
            session.step_forward()
        session.selected_pieces = {three}
        session.delete_selected()
        self.assertEqual(session.step_ids, [one, two])
        self.assertEqual(session.step, 1)

    def test_a_sketch_that_is_not_a_path_cannot_step(self):
        from wop.core.sketch.modes import TURNING

        self.assertFalse(SketchSession(target=SketchTarget(TURNING, "t")).can_step)


if __name__ == "__main__":
    unittest.main()
