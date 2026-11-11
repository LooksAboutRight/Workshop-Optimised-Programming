import math
import unittest

from tests import reference_data
from wop.core.constants import ARC_MAX_DEVIATION_MM
from wop.core.geometry import (
    ArcDirection,
    ArcSegment,
    LineSegment,
    Point,
    polyline_length,
    segments_to_polyline,
    signed_area,
)

ORIGIN = Point(0, 0)


class PointTests(unittest.TestCase):
    def test_distance(self):
        self.assertAlmostEqual(Point(0, 0).distance_to(Point(3, 4)), 5)

    def test_is_close_uses_tolerance(self):
        self.assertTrue(Point(1, 1).is_close(Point(1, 1.0000001)))
        self.assertFalse(Point(1, 1).is_close(Point(1, 1.01)))


class LineTests(unittest.TestCase):
    def test_length(self):
        self.assertAlmostEqual(LineSegment(Point(0, 0), Point(3, 4)).length, 5)

    def test_point_at_is_exact_at_both_ends(self):
        line = LineSegment(Point(1.1, 2.2), Point(7.7, -3.3))
        self.assertEqual(line.point_at(0), line.start)
        self.assertEqual(line.point_at(1), line.end)

    def test_midpoint(self):
        mid = LineSegment(Point(0, 0), Point(10, -20)).point_at(0.5)
        self.assertTrue(mid.is_close(Point(5, -10)))


class ArcTests(unittest.TestCase):
    def test_quarter_circle_ccw(self):
        arc = ArcSegment(Point(10, 0), Point(0, 10), ORIGIN, ArcDirection.CCW)
        self.assertAlmostEqual(arc.radius, 10)
        self.assertAlmostEqual(arc.sweep, math.pi / 2)
        self.assertAlmostEqual(arc.length, 10 * math.pi / 2)

    def test_same_points_clockwise_is_the_long_way_round(self):
        arc = ArcSegment(Point(10, 0), Point(0, 10), ORIGIN, ArcDirection.CW)
        self.assertAlmostEqual(arc.sweep, 3 * math.pi / 2)

    def test_half_circle(self):
        arc = ArcSegment(Point(10, 0), Point(-10, 0), ORIGIN, ArcDirection.CCW)
        self.assertAlmostEqual(arc.sweep, math.pi)

    def test_full_circle(self):
        arc = ArcSegment(Point(10, 0), Point(10, 0), ORIGIN, ArcDirection.CCW)
        self.assertTrue(arc.is_full_circle)
        self.assertAlmostEqual(arc.sweep, math.tau)
        self.assertAlmostEqual(arc.length, math.tau * 10)

    def test_start_and_end_must_be_on_the_same_circle(self):
        with self.assertRaises(ValueError):
            ArcSegment(Point(10, 0), Point(0, 11), ORIGIN, ArcDirection.CCW)

    def test_radius_zero_is_rejected(self):
        with self.assertRaises(ValueError):
            ArcSegment(ORIGIN, ORIGIN, ORIGIN, ArcDirection.CCW)

    def test_point_at_ends_and_middle(self):
        arc = ArcSegment(Point(10, 0), Point(0, 10), ORIGIN, ArcDirection.CCW)
        self.assertEqual(arc.point_at(0), arc.start)
        self.assertEqual(arc.point_at(1), arc.end)
        expected = Point(10 * math.cos(math.pi / 4), 10 * math.sin(math.pi / 4))
        self.assertTrue(arc.point_at(0.5).is_close(expected))

    def test_clockwise_point_at_goes_the_other_way(self):
        arc = ArcSegment(Point(10, 0), Point(0, -10), ORIGIN, ArcDirection.CW)
        self.assertAlmostEqual(arc.sweep, math.pi / 2)
        self.assertTrue(arc.point_at(0.5).z < 0)


class PolylineTests(unittest.TestCase):
    def test_polyline_stays_within_deviation_and_inside_the_circle(self):
        arc = ArcSegment(Point(25, 0), Point(0, 25), ORIGIN, ArcDirection.CCW)
        points = arc.to_polyline(ARC_MAX_DEVIATION_MM)
        self.assertTrue(points[0].is_close(arc.start))
        self.assertTrue(points[-1].is_close(arc.end))
        for a, b in zip(points, points[1:]):
            mid = Point((a.x + b.x) / 2, (a.z + b.z) / 2)
            deviation = arc.radius - mid.distance_to(arc.center)
            self.assertGreaterEqual(deviation, -1e-9)
            self.assertLessEqual(deviation, ARC_MAX_DEVIATION_MM + 1e-9)

    def test_full_circle_has_more_than_two_points(self):
        arc = ArcSegment(Point(5, 0), Point(5, 0), Point(0, 0), ArcDirection.CCW)
        self.assertGreater(len(arc.to_polyline()), 4)

    def test_nonpositive_deviation_is_rejected(self):
        arc = ArcSegment(Point(5, 0), Point(0, 5), ORIGIN, ArcDirection.CCW)
        with self.assertRaises(ValueError):
            arc.to_polyline(0)

    def test_chaining_removes_duplicate_joints(self):
        segments = [
            LineSegment(Point(0, 0), Point(1, 0)),
            LineSegment(Point(1, 0), Point(1, 1)),
        ]
        self.assertEqual(len(segments_to_polyline(segments)), 3)


class AreaTests(unittest.TestCase):
    def test_counter_clockwise_square_is_positive(self):
        square = [Point(0, 0), Point(2, 0), Point(2, 2), Point(0, 2)]
        self.assertAlmostEqual(signed_area(square), 4)
        self.assertAlmostEqual(signed_area(list(reversed(square))), -4)


class ReferenceProfileTests(unittest.TestCase):
    def test_stepped_shaft(self):
        points = segments_to_polyline(reference_data.stepped_shaft_profile())
        self.assertAlmostEqual(abs(signed_area(points)), reference_data.STEPPED_SHAFT_AREA_MM2)
        self.assertAlmostEqual(polyline_length(points), reference_data.STEPPED_SHAFT_PERIMETER_MM)
        # the profile runs clockwise in the (x, z) plane
        self.assertLess(signed_area(points), 0)

    def test_rounded_end(self):
        segments = reference_data.rounded_end_profile()
        points = segments_to_polyline(segments)
        self.assertAlmostEqual(
            abs(signed_area(points)), reference_data.ROUNDED_END_AREA_MM2, delta=0.01
        )
        exact_perimeter = sum(segment.length for segment in segments)
        self.assertAlmostEqual(exact_perimeter, reference_data.ROUNDED_END_PERIMETER_MM)

    def test_profiles_are_closed(self):
        for profile in (
            reference_data.stepped_shaft_profile(),
            reference_data.rounded_end_profile(),
        ):
            self.assertTrue(profile[0].start.is_close(profile[-1].end))
            for a, b in zip(profile, profile[1:]):
                self.assertTrue(a.end.is_close(b.start))


if __name__ == "__main__":
    unittest.main()
