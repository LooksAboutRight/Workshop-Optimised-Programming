import unittest

from wop.core.constants import SAFE_POINT_KEY
from wop.core.geometry import ArcDirection, LineSegment, Point
from wop.core.sketch.locked import LockedPoint, sync_locked
from wop.core.sketch.model import Sketch
from wop.core.sketch.modes import PATH, contour_from_sketch, problems
from wop.core.sketch.path_walk import walk_path
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_target import SketchTarget

SAFE = LockedPoint(SAFE_POINT_KEY, 30, 5)


def _sketch():
    sketch = Sketch()
    sync_locked(sketch, (SAFE,), ())
    return sketch, sketch.locked_points[SAFE_POINT_KEY]


def _line(sketch, start, end):
    return sketch.add_line(start, end)


class WalkTests(unittest.TestCase):
    def test_a_path_goes_piece_after_piece_from_the_safe_point(self):
        sketch, safe = _sketch()
        a, b = sketch.add_point(30, -10), sketch.add_point(20, -10)
        first, second = _line(sketch, safe, a), _line(sketch, a, b)
        walked, found = walk_path(sketch)
        self.assertEqual(found, [])
        self.assertEqual([(p.line_id, forward) for p, forward in walked], [(first, True), (second, True)])
        self.assertEqual(problems(sketch, PATH), [])

    def test_a_piece_drawn_the_other_way_is_walked_backwards(self):
        sketch, safe = _sketch()
        a = sketch.add_point(30, -10)
        _line(sketch, a, safe)  # drawn towards the safe point
        walked, found = walk_path(sketch)
        self.assertEqual(found, [])
        self.assertEqual([forward for _p, forward in walked], [False])

    def test_the_path_may_come_back_along_a_line_and_cross_itself(self):
        sketch, safe = _sketch()
        a, b, c = sketch.add_point(30, -10), sketch.add_point(20, -10), sketch.add_point(20, 5)
        one, two = _line(sketch, safe, a), _line(sketch, a, b)
        back = _line(sketch, b, a)  # the same line again, the other way
        three = _line(sketch, a, c)  # and on: three pieces meet at `a`
        walked, found = walk_path(sketch)
        self.assertEqual(found, [])
        self.assertEqual([p.line_id for p, _f in walked], [one, two, back, three])
        self.assertEqual(problems(sketch, PATH), [])

    def test_points_at_the_same_place_are_one_point(self):
        sketch, safe = _sketch()
        a, same = sketch.add_point(30, -10), sketch.add_point(30, -10)
        _line(sketch, safe, a)
        _line(sketch, same, sketch.add_point(10, -10))
        self.assertEqual(problems(sketch, PATH), [])

    def test_the_problems_are_named(self):
        sketch, safe = _sketch()
        self.assertTrue(any("Draw the path" in p for p in problems(sketch, PATH)))
        far = sketch.add_point(10, 10)
        _line(sketch, far, sketch.add_point(10, 20))  # does not touch the safe point
        self.assertTrue(any("Draw the path" in p for p in problems(sketch, PATH)))
        a = sketch.add_point(30, -10)
        _line(sketch, safe, a)
        self.assertTrue(any("do not follow the path" in p for p in problems(sketch, PATH)))
        stray = next(i for i, line in sketch.lines.items() if line.start == far)
        sketch.update_piece(stray, construction=True)
        self.assertEqual(problems(sketch, PATH), [])

    def test_an_arc_is_a_piece_of_the_path_and_a_circle_is_not(self):
        sketch, safe = _sketch()
        centre, end = sketch.add_point(30, -10), sketch.add_point(25, -10)
        sketch.add_arc(centre, safe, end, ArcDirection.CCW)
        walked, found = walk_path(sketch)
        self.assertEqual(found, [])
        self.assertEqual(len(walked), 1)
        circle = sketch.add_point(50, 0)  # a circle has its start and end on one point: the walk names it
        sketch.add_arc(sketch.add_point(55, 0), circle, circle)
        self.assertTrue(any("circle" in p for p in walk_path(sketch)[1]))

    def test_the_contour_of_a_path_is_its_segments_in_travel_order(self):
        sketch, safe = _sketch()
        a = sketch.add_point(30, -10)
        _line(sketch, a, safe)
        contour = contour_from_sketch(sketch, PATH, "path", "Path")
        self.assertEqual(contour.segments, (LineSegment(Point(30, 5), Point(30, -10)),))
        self.assertIsNotNone(contour.sketch)


class CornerOfAPathTests(unittest.TestCase):
    def _corner(self, first_feed, second_feed, rapid=False):
        from wop.core.sketch.corners import chamfer_corner, fillet_corner

        sketch, safe = _sketch()
        corner, end = sketch.add_point(30, -10), sketch.add_point(20, -10)
        one, two = _line(sketch, safe, corner), _line(sketch, corner, end)
        for piece, feed in ((one, first_feed), (two, second_feed)):
            if feed:
                sketch.piece_feeds[piece] = feed
            if rapid:
                sketch.rapid_pieces.add(piece)
        return sketch, corner, (chamfer_corner, fillet_corner)

    def _feeds_after(self, make, first_feed, second_feed):
        sketch, corner, makers = self._corner(first_feed, second_feed)
        makers[make](sketch, corner, 1)
        walked, found = walk_path(sketch)
        self.assertEqual(found, [])
        return [sketch.piece_feeds.get(piece.line_id if hasattr(piece, "line_id") else piece.arc_id) for piece, _f in walked]

    def test_a_corner_between_two_pieces_with_the_same_feed_has_that_feed_too(self):
        for make in (0, 1):  # chamfer, fillet
            self.assertEqual(self._feeds_after(make, 0.2, 0.2), [0.2, 0.2, 0.2])

    def test_a_corner_between_pieces_with_other_feeds_has_none_and_the_pieces_keep_theirs(self):
        for make in (0, 1):
            self.assertEqual(self._feeds_after(make, 0.2, 0.4), [0.2, None, 0.4])
            self.assertEqual(self._feeds_after(make, 0.2, None), [0.2, None, None])

    def test_a_corner_between_two_rapid_lines_is_a_rapid_and_the_shortened_lines_stay_rapid(self):
        from wop.core.sketch.corners import chamfer_corner

        sketch, corner, _makers = self._corner(None, None, rapid=True)
        chamfer_corner(sketch, corner, 1)
        walked, _found = walk_path(sketch)
        self.assertEqual([piece.line_id in sketch.rapid_pieces for piece, _f in walked], [True, True, True])
        sketch, corner, _makers = self._corner(None, None)
        sketch.rapid_pieces.add(min(sketch.lines))  # only the first one
        chamfer_corner(sketch, corner, 1)
        walked, _found = walk_path(sketch)
        self.assertEqual([piece.line_id in sketch.rapid_pieces for piece, _f in walked], [True, False, False])


class FlagTests(unittest.TestCase):
    def _session(self):
        sketch, safe = _sketch()
        a = sketch.add_point(30, -10)
        line = _line(sketch, safe, a)
        return SketchSession(sketch, SketchTarget(PATH, "p", locked_points=(SAFE,))), line

    def test_a_line_is_a_rapid_move_after_the_button_and_a_feed_move_after_it_again(self):
        session, line = self._session()
        session.selected_pieces = {line}
        self.assertTrue(session.available_modify("rapid"))
        self.assertTrue(session.toggle_rapid())
        self.assertEqual(session.sketch.rapid_pieces, {line})
        session.selected_pieces = {line}
        session.toggle_rapid()
        self.assertEqual(session.sketch.rapid_pieces, set())

    def test_an_arc_cannot_be_a_rapid_move(self):
        session, _line_id = self._session()
        sketch = session.sketch
        arc = sketch.add_arc(sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(0, 5))
        session.selected_pieces = {arc}
        self.assertFalse(session.available_modify("rapid"))
        self.assertFalse(session.toggle_rapid())

    def test_a_feed_of_its_own_is_set_and_taken_away(self):
        session, line = self._session()
        session.selected_pieces = {line}
        self.assertTrue(session.set_piece_feed(0.25))
        self.assertEqual(session.sketch.piece_feeds, {line: 0.25})
        self.assertTrue(session.set_piece_feed(None))
        self.assertEqual(session.sketch.piece_feeds, {})

    def test_flags_and_feeds_are_saved_and_follow_their_pieces(self):
        session, line = self._session()
        session.sketch.rapid_pieces.add(line)
        session.sketch.piece_feeds[line] = 0.3
        again = sketch_from_dict(sketch_to_dict(session.sketch))
        self.assertEqual((again.rapid_pieces, again.piece_feeds), ({line}, {line: 0.3}))
        again.delete_piece(line)
        self.assertEqual((again.rapid_pieces, again.piece_feeds), (set(), {}))


if __name__ == "__main__":
    unittest.main()
