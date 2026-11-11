import unittest

from tests import reference_data
from wop.core.contour_check import Crossing, find_crossings
from wop.core.geometry import ArcDirection, LineSegment, Point, arc_from_endpoints


def line(x1, z1, x2, z2):
    return LineSegment(Point(x1, z1), Point(x2, z2))


class CrossingTests(unittest.TestCase):
    def test_reference_profiles_have_no_crossings(self):
        for profile in (
            reference_data.stepped_shaft_profile(),
            reference_data.rounded_end_profile(),
        ):
            self.assertEqual(find_crossings(profile, closed=True), [])

    def test_bowtie_is_reported_with_both_element_numbers(self):
        bowtie = [
            line(0, 0, 10, 10),
            line(10, 10, 10, 0),
            line(10, 0, 0, 10),
            line(0, 10, 0, 0),
        ]
        crossings = find_crossings(bowtie, closed=True)
        self.assertEqual(crossings, [Crossing(0, 2)])

    def test_fold_back_spike_is_reported(self):
        spike = [line(0, 0, 10, 0), line(10, 0, 5, 0), line(5, 0, 5, -5), line(5, -5, 0, -5)]
        crossings = find_crossings(spike, closed=False)
        self.assertIn(Crossing(0, 1), crossings)

    def test_touching_non_adjacent_segments_are_reported(self):
        touching = [
            line(0, 0, 10, 0),
            line(10, 0, 10, -10),
            line(10, -10, 5, 0),
            line(5, 0, 0, -10),
        ]
        self.assertTrue(find_crossings(touching, closed=False))

    def test_smooth_joint_between_line_and_arc_is_not_a_crossing(self):
        chain = [
            line(0, 0, 7, 0),
            arc_from_endpoints(Point(7, 0), Point(10, -3), 3, ArcDirection.CW),
            line(10, -3, 10, -20),
        ]
        self.assertEqual(find_crossings(chain, closed=False), [])


if __name__ == "__main__":
    unittest.main()
