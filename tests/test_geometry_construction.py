import math
import unittest

from tests import reference_data
from wop.core.geometry import (
    ArcDirection,
    LineSegment,
    Point,
    arc_from_endpoints,
    segments_intersect,
)

ORIGIN = Point(0, 0)


class ArcFromEndpointsTests(unittest.TestCase):
    def test_quarter_circle_ccw(self):
        arc = arc_from_endpoints(Point(10, 0), Point(0, 10), 10, ArcDirection.CCW)
        self.assertTrue(arc.center.is_close(ORIGIN))
        self.assertAlmostEqual(arc.sweep, math.pi / 2)

    def test_quarter_circle_cw(self):
        arc = arc_from_endpoints(Point(10, 0), Point(0, -10), 10, ArcDirection.CW)
        self.assertTrue(arc.center.is_close(ORIGIN))
        self.assertAlmostEqual(arc.sweep, math.pi / 2)

    def test_large_arc_sweeps_three_quarters(self):
        arc = arc_from_endpoints(Point(10, 0), Point(0, 10), 10, ArcDirection.CCW, large_arc=True)
        self.assertTrue(arc.center.is_close(Point(10, 10)))
        self.assertAlmostEqual(arc.sweep, 3 * math.pi / 2)

    def test_matches_the_reference_round(self):
        reference = reference_data.rounded_end_profile()[1]
        arc = arc_from_endpoints(reference.start, reference.end, 3, ArcDirection.CW)
        self.assertTrue(arc.center.is_close(reference.center))

    def test_half_circle_when_radius_is_half_the_distance(self):
        arc = arc_from_endpoints(Point(-5, 0), Point(5, 0), 5, ArcDirection.CCW)
        self.assertAlmostEqual(arc.sweep, math.pi)

    def test_radius_too_small(self):
        with self.assertRaises(ValueError):
            arc_from_endpoints(Point(0, 0), Point(30, 0), 10, ArcDirection.CCW)

    def test_same_point_and_zero_radius_are_rejected(self):
        with self.assertRaises(ValueError):
            arc_from_endpoints(Point(1, 1), Point(1, 1), 5, ArcDirection.CCW)
        with self.assertRaises(ValueError):
            arc_from_endpoints(Point(0, 0), Point(1, 0), 0, ArcDirection.CCW)


class SegmentsIntersectTests(unittest.TestCase):
    def test_crossing(self):
        self.assertTrue(segments_intersect(Point(0, 0), Point(4, 4), Point(0, 4), Point(4, 0)))

    def test_parallel_apart(self):
        self.assertFalse(segments_intersect(Point(0, 0), Point(4, 0), Point(0, 1), Point(4, 1)))

    def test_touching_at_an_end(self):
        self.assertTrue(segments_intersect(Point(0, 0), Point(4, 0), Point(4, 0), Point(4, 4)))

    def test_t_junction(self):
        self.assertTrue(segments_intersect(Point(0, 0), Point(4, 0), Point(2, 0), Point(2, 3)))

    def test_collinear_overlap_and_collinear_apart(self):
        self.assertTrue(segments_intersect(Point(0, 0), Point(4, 0), Point(2, 0), Point(6, 0)))
        self.assertFalse(segments_intersect(Point(0, 0), Point(1, 0), Point(2, 0), Point(3, 0)))

    def test_near_miss(self):
        self.assertFalse(segments_intersect(Point(0, 0), Point(4, 0), Point(5, -1), Point(5, 1)))

    def test_line_segment_type_is_untouched(self):
        line = LineSegment(Point(0, 0), Point(1, 0))
        self.assertAlmostEqual(line.length, 1)


if __name__ == "__main__":
    unittest.main()
