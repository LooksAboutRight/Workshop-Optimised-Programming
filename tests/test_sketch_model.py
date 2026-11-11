import unittest

from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point
from wop.core.sketch.loops import chain_segments, find_chains
from wop.core.sketch.model import Sketch, SketchError, arc_from_three_points


def _square() -> Sketch:
    sketch = Sketch()
    a, b, c, d = (sketch.add_point(x, z) for x, z in ((0, 0), (10, 0), (10, 10), (0, 10)))
    for start, end in ((a, b), (b, c), (c, d), (d, a)):
        sketch.add_line(start, end)
    return sketch


class SketchModelTests(unittest.TestCase):
    def test_line_needs_two_points(self):
        sketch = Sketch()
        a = sketch.add_point(0, 0)
        with self.assertRaises(SketchError):
            sketch.add_line(a, a)

    def test_delete_piece_drops_unused_points(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(1, 0)
        line = sketch.add_line(a, b)
        sketch.delete_piece(line)
        self.assertEqual(sketch.points, {})

    def test_merge_points_joins_and_removes_collapsed_pieces(self):
        sketch = Sketch()
        a, b, c = sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(5.0001, 0)
        sketch.add_line(a, b)
        sketch.add_line(c, b)
        sketch.merge_points(b, c)
        self.assertEqual(len(sketch.lines), 1)

    def test_three_points_arc(self):
        centre, direction = arc_from_three_points(Point(1, 0), Point(0, 1), Point(-1, 0))
        self.assertAlmostEqual(centre.x, 0)
        self.assertAlmostEqual(centre.z, 0)
        self.assertIs(direction, ArcDirection.CCW)
        _, direction = arc_from_three_points(Point(-1, 0), Point(0, 1), Point(1, 0))
        self.assertIs(direction, ArcDirection.CW)

    def test_three_points_on_a_line_fail(self):
        with self.assertRaises(SketchError):
            arc_from_three_points(Point(0, 0), Point(1, 0), Point(2, 0))

    def test_arc_end_is_put_on_the_circle(self):
        sketch = Sketch()
        centre, start, end = sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(0, 9)
        sketch.add_arc(centre, start, end)
        segment = sketch.segment(sketch.arcs[next(iter(sketch.arcs))])
        self.assertIsInstance(segment, ArcSegment)
        self.assertAlmostEqual(segment.end.z, 5)


class SketchLoopTests(unittest.TestCase):
    def test_square_is_one_closed_chain(self):
        chains = find_chains(_square())
        self.assertEqual(len(chains), 1)
        self.assertTrue(chains[0].closed)
        self.assertEqual(len(chains[0].pieces), 4)

    def test_open_profile_in_any_drawing_direction(self):
        sketch = Sketch()
        a, b, c = sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(5, 5)
        sketch.add_line(b, a)  # drawn against the travel direction
        sketch.add_line(b, c)
        chains = find_chains(sketch)
        self.assertEqual(len(chains), 1)
        self.assertFalse(chains[0].closed)
        segments = chain_segments(sketch, chains[0])
        for before, after in zip(segments, segments[1:]):
            self.assertTrue(before.end.is_close(after.start))

    def test_construction_pieces_are_left_out(self):
        sketch = _square()
        a, c = sketch.add_point(0, 0), sketch.add_point(10, 10)
        sketch.add_line(a, c, construction=True)
        self.assertEqual(len(find_chains(sketch)), 1)

    def test_branch_is_an_error(self):
        sketch = Sketch()
        hub = sketch.add_point(0, 0)
        for x, z in ((1, 0), (0, 1), (-1, 0)):
            sketch.add_line(hub, sketch.add_point(x, z))
        with self.assertRaises(SketchError):
            find_chains(sketch)

    def test_reversed_arc_is_turned_round(self):
        sketch = Sketch()
        centre, start, end = sketch.add_point(0, 0), sketch.add_point(1, 0), sketch.add_point(0, 1)
        sketch.add_arc(centre, start, end)  # CCW from (1,0) to (0,1)
        tail = sketch.add_point(0, 5)
        sketch.add_line(end, tail)
        # walk starting at the tail: line backwards, then the arc backwards
        chains = find_chains(sketch)
        segments = chain_segments(sketch, chains[0])
        self.assertEqual(len(segments), 2)
        arc = next(s for s in segments if isinstance(s, ArcSegment))
        line = next(s for s in segments if isinstance(s, LineSegment))
        self.assertTrue(line.end.is_close(arc.start) or arc.end.is_close(line.start))


if __name__ == "__main__":
    unittest.main()
