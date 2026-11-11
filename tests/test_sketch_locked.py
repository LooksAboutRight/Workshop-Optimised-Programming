import copy
import unittest

from wop.core.geometry import ArcDirection, Point
from wop.core.sketch.locked import LockedArc, LockedLine, LockedPoint, locked_changed, sync_locked
from wop.core.sketch.model import Sketch
from wop.core.sketch.modes import TURNING
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.core.sketch.solver import analyse, solve
from wop.ui.sketch_constants import LOCKED_MESSAGE
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_target import SketchTarget

SAFE = LockedPoint("safe point", 40, 5)
FRONT = LockedPoint("front corner", 20, 0)
BACK = LockedPoint("back corner", 20, -30)
OUTLINE = LockedLine("outline", "front corner", "back corner")


def _locked_sketch():
    sketch = Sketch()
    notes = sync_locked(sketch, (SAFE, FRONT, BACK), (OUTLINE,))
    return sketch, notes


def _with_a_line_from_the_safe_point(sketch):
    safe = sketch.locked_points["safe point"]
    mine = sketch.add_point(10, 5)
    sketch.add_line(mine, safe)
    sketch.add_constraint("fixed", (mine,), (10, 5))
    sketch.add_constraint("vertical", (mine, safe))
    return mine, safe


class SyncTests(unittest.TestCase):
    def test_locked_things_are_made_and_found_again_by_their_key(self):
        sketch, notes = _locked_sketch()
        self.assertEqual(notes, [])
        self.assertEqual(set(sketch.locked_points), {"safe point", "front corner", "back corner"})
        self.assertTrue(sketch.lines[sketch.locked_lines["outline"]].construction)  # never part of the outline of the sketch
        ids = dict(sketch.locked_points)
        sync_locked(sketch, (SAFE, LockedPoint("front corner", 25, 0), BACK), (OUTLINE,))
        self.assertEqual(sketch.locked_points, ids)  # the same ids: a dimension to them keeps pointing at them
        self.assertEqual(sketch.points[ids["front corner"]].position, Point(25, 0))

    def test_a_relation_to_a_locked_point_follows_it(self):
        sketch, _ = _locked_sketch()
        mine = sketch.add_point(30, 5)
        safe = sketch.locked_points["safe point"]
        sketch.add_line(mine, safe)
        sketch.add_constraint("vertical", (mine, safe))
        notes = sync_locked(sketch, (LockedPoint("safe point", 40, 8), FRONT, BACK), (OUTLINE,))
        self.assertEqual(notes, [])
        self.assertAlmostEqual(sketch.points[mine].z, 8)  # solved to the new position
        self.assertEqual(sketch.points[safe].position, Point(40, 8))

    def test_what_cannot_be_solved_any_more_is_removed_and_reported(self):
        sketch, _ = _locked_sketch()
        _with_a_line_from_the_safe_point(sketch)
        self.assertEqual(sync_locked(sketch, (SAFE, FRONT, BACK), (OUTLINE,)), [])
        notes = sync_locked(sketch, (LockedPoint("safe point", 40, 9), FRONT, BACK), (OUTLINE,))
        self.assertTrue(notes)  # "vertical" (same Z) cannot hold: the other end is fixed at z = 5
        self.assertTrue(solve(sketch).converged)

    def test_a_locked_thing_that_is_no_longer_supplied_goes(self):
        sketch, _ = _locked_sketch()
        sync_locked(sketch, (SAFE,), ())
        self.assertEqual(set(sketch.locked_points), {"safe point"})
        self.assertEqual(sketch.locked_lines, {})
        self.assertEqual(len(sketch.points), 1)

    def test_a_locked_point_that_a_line_uses_stays_as_an_ordinary_point(self):
        sketch, _ = _locked_sketch()
        sketch.add_line(sketch.add_point(30, 5), sketch.locked_points["safe point"])
        sync_locked(sketch, (), ())
        self.assertEqual(sketch.locked_points, {})
        self.assertEqual(len(sketch.lines), 1)

    def test_locked_things_are_saved_with_the_sketch(self):
        sketch, _ = _locked_sketch()
        again = sketch_from_dict(sketch_to_dict(sketch))
        self.assertEqual(again.locked_points, sketch.locked_points)
        self.assertEqual(again.locked_lines, sketch.locked_lines)

    def test_the_solver_holds_locked_points_and_counts_them_as_fixed(self):
        sketch, _ = _locked_sketch()
        self.assertEqual(analyse(sketch).fixed_points, frozenset(sketch.locked_points.values()))
        self.assertFalse(locked_changed(sketch, copy.deepcopy(sketch)))
        moved = copy.deepcopy(sketch)
        moved.move_point(moved.locked_points["safe point"], 1, 1)
        self.assertTrue(locked_changed(sketch, moved))


def _part(count):
    """A part outline of `count` lines along Z, as one group: keys 'part/0' ..."""
    points = tuple(LockedPoint(f"part/p{i}", 20, -10 * i) for i in range(count + 1))
    lines = tuple(LockedLine(f"part/{i}", f"part/p{i}", f"part/p{i + 1}") for i in range(count))
    return points, lines


class ArcAndGroupTests(unittest.TestCase):
    def test_a_locked_arc_is_made_pinned_and_saved(self):
        sketch = Sketch()
        points = (LockedPoint("a/c", 0, 0), LockedPoint("a/s", 5, 0), LockedPoint("a/e", 0, 5))
        arc = LockedArc("a/arc", "a/c", "a/s", "a/e", ArcDirection.CCW)
        sync_locked(sketch, points, (), (arc,))
        arc_id = sketch.locked_arcs["a/arc"]
        self.assertTrue(sketch.arcs[arc_id].construction)
        self.assertTrue(sketch.is_locked_piece(arc_id))
        again = sketch_from_dict(sketch_to_dict(sketch))
        self.assertEqual(again.locked_arcs, sketch.locked_arcs)
        self.assertEqual(again.locked_groups, sketch.locked_groups)
        moved = copy.deepcopy(sketch)
        moved.update_piece(arc_id, direction=ArcDirection.CW)
        self.assertTrue(locked_changed(sketch, moved))

    def test_a_dimension_to_a_group_that_kept_its_pieces_stays(self):
        sketch = Sketch()
        sync_locked(sketch, *_part(3))
        mine = sketch.add_point(30, -5)
        sketch.add_line(mine, sketch.locked_points["part/p1"])
        sketch.add_constraint("vertical", (mine, sketch.locked_points["part/p1"]))
        notes = sync_locked(sketch, *(_part(3)[0][:1] + tuple(LockedPoint(f"part/p{i}", 22, -10 * i) for i in range(1, 4)), _part(3)[1]))
        self.assertEqual(notes, [])
        self.assertEqual(len(sketch.constraints), 1)

    def test_every_relation_to_a_group_that_changed_its_pieces_is_dropped(self):
        sketch = Sketch()
        sync_locked(sketch, *_part(3))
        mine = sketch.add_point(30, -5)
        sketch.add_line(mine, sketch.locked_points["part/p1"])
        sketch.add_constraint("vertical", (mine, sketch.locked_points["part/p1"]))
        other = sketch.add_point(50, 0)
        sketch.add_line(other, sketch.add_point(60, 0))
        sketch.add_constraint("fixed", (other,), (50, 0))  # a relation of its own: stays
        notes = sync_locked(sketch, *_part(4))
        self.assertTrue(any("shape changed" in n for n in notes))
        self.assertEqual([c.kind for c in sketch.constraints.values()], ["fixed"])

    def test_a_line_that_became_an_arc_counts_as_a_change(self):
        sketch = Sketch()
        points = (LockedPoint("a/c", 0, 0), LockedPoint("a/s", 5, 0), LockedPoint("a/e", 0, 5))
        sync_locked(sketch, points, (LockedLine("a/x", "a/s", "a/e"),), ())
        mine = sketch.add_point(9, 9)
        sketch.add_line(mine, sketch.locked_points["a/s"])
        sketch.add_constraint("vertical", (mine, sketch.locked_points["a/s"]))
        notes = sync_locked(sketch, points, (), (LockedArc("a/x", "a/c", "a/s", "a/e"),))
        self.assertTrue(any("shape changed" in n for n in notes))
        self.assertEqual(len(sketch.constraints), 0)


class SessionTests(unittest.TestCase):
    def _session(self):
        target = SketchTarget(TURNING, "t", locked_points=(SAFE, FRONT, BACK), locked_lines=(OUTLINE,))
        return SketchSession(target=target)

    def test_a_locked_point_cannot_be_dragged_or_deleted(self):
        session = self._session()
        safe = session.sketch.locked_points["safe point"]
        session.press(Point(40, 5), 1)
        self.assertEqual(session.message, LOCKED_MESSAGE)
        session.drag(Point(50, 9), 1)
        session.release(Point(50, 9), 1)
        self.assertEqual(session.sketch.points[safe].position, Point(40, 5))
        session.selected_points = {safe}
        session.delete_selected()
        self.assertIn(safe, session.sketch.points)
        self.assertEqual(session.message, LOCKED_MESSAGE)

    def test_a_locked_line_cannot_be_deleted_trimmed_or_made_a_real_line(self):
        session = self._session()
        line = session.sketch.locked_lines["outline"]
        session.selected_pieces = {line}
        session.delete_selected()
        self.assertIn(line, session.sketch.lines)
        session.selected_pieces = {line}
        self.assertFalse(session.toggle_construction())
        self.assertTrue(session.sketch.lines[line].construction)
        self.assertEqual(session.message, LOCKED_MESSAGE)
        session.trim_at(Point(20, -15), 1)
        self.assertIn(line, session.sketch.lines)

    def test_a_line_from_a_locked_point_stretches_when_dragged(self):
        session = self._session()
        safe = session.sketch.locked_points["safe point"]
        mine = session.sketch.add_point(30, 5)
        piece = session.sketch.add_line(safe, mine)
        session.selected_pieces = {piece}
        session.press(Point(35, 5), 1)
        session.drag(Point(35, 10), 1)
        session.release(Point(35, 10), 1)
        self.assertEqual(session.sketch.points[safe].position, Point(40, 5))
        self.assertNotEqual(session.sketch.points[mine].position, Point(30, 5))

    def test_the_notes_say_what_was_removed_when_the_session_opens(self):
        sketch, _ = _locked_sketch()
        _with_a_line_from_the_safe_point(sketch)
        target = SketchTarget(TURNING, "t", locked_points=(LockedPoint("safe point", 40, 9), FRONT, BACK), locked_lines=(OUTLINE,))
        self.assertTrue(SketchSession(sketch, target).notes)


if __name__ == "__main__":
    unittest.main()


class DimensionToTheOutlineTests(unittest.TestCase):
    """A point is dimensioned to a locked line (the part before a custom path block) as a distance, never as a diameter."""

    def _session(self):
        from wop.core.sketch.modes import PATH

        target = SketchTarget(PATH, "p", locked_points=(SAFE, FRONT, BACK), locked_lines=(OUTLINE,))
        session = SketchSession(target=target)
        mine = session.sketch.add_point(25, -15)
        session.sketch.add_line(session.sketch.locked_points["safe point"], mine)
        return session, mine

    def test_a_point_and_a_locked_line_give_a_distance_to_the_line_on_either_side(self):
        for mouse in (Point(22, -15), Point(10, -15)):  # between the point and the line, and across the line
            session, mine = self._session()
            session.set_tool("dimension")
            session.dimension_click(Point(25, -15), 0.1)  # the point
            session.dimension_click(Point(20, -10), 0.1)  # the locked line (x = 20)
            self.assertEqual([k for k, _ in session.dim_picks], ["point", "centre"])
            session.dimension_click(mouse, 0.1)
            kinds = [c.kind for c in session.sketch.constraints.values()]
            self.assertEqual(kinds, ["distance_line"], mouse)
            self.assertAlmostEqual(next(iter(session.sketch.constraints.values())).values[0], 5)

    def test_the_dimension_is_kept_and_follows_the_line_when_the_part_moves(self):
        session, mine = self._session()
        session.set_tool("dimension")
        session.dimension_click(Point(25, -15), 0.1)
        session.dimension_click(Point(20, -10), 0.1)
        session.dimension_click(Point(22, -15), 0.1)
        notes = sync_locked(session.sketch, (SAFE, LockedPoint("front corner", 22, 0), LockedPoint("back corner", 22, -30)), (OUTLINE,))
        self.assertEqual(notes, [])
        self.assertAlmostEqual(session.sketch.points[mine].x, 27)
